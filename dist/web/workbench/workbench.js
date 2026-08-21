/**
 * workbench.js — 工作台 v2
 *
 * 布局（4列）：
 *   左列     [1] 今日清单 + [2] 今日详情
 *   中列     [3] 我的主业务 / [4] 条目链接  （双 tab，共享同一面板）
 *   日历列   [C] 小日历 + 项目健康度
 *   右侧栏   [4] 我关注的 + [5] 变更预警 + [6] 项目状态  （默认关闭）
 *
 * 键盘：
 *   1–7      切换面板（btop 风格）
 *             3 = 显示中列并切到 [3] tab；4 = 显示中列并切到 [4] tab
 *             5/6/7 = 切换右侧通知栏中的具体面板
 *   c        切换日历列
 *   f        筛选当前聚焦面板
 *   Tab      [4] 聚焦时：循环切换链接
 *   ↑↓       移动行选中
 *   Enter    打开选中条目
 *   Escape   收起筛选 / 取消聚焦
 */
(function () {
  'use strict';

  // ── localStorage 用户隔离 ────────────────────────────────────────────────
  // 用当前登录用户的 GID 作为 key 前缀，防止同一台机器不同账户共享状态
  const _userGid = (() => {
    try { const u = window.parent?._authUser; return u?.gid || u?.user_gid || ''; } catch { return ''; }
  })();
  function _lsk(base) { return _userGid ? `${_userGid}:${base}` : base; }

  // ── 状态 ────────────────────────────────────────────────────────────────
  let _focusedPanel = null;   // 1-7 or 'c'
  let _selectedIdx  = {};
  let _panelData    = {};
  let _filterText   = {};
  let _currentUser  = null;

  // 面板2 文件树状态
  let _treeOpen     = _loadTreeOpen();    // { sectionKey: bool } 展开状态
  let _treeSections = null;               // 上次渲染的 sections（折叠重渲染用）
  const _LS_TREE    = 'wb:p2-tree-open';  // localStorage key
  let _recentFiles  = _loadRecentFiles(); // 最近查看的清单（最多5条）

  let _panel1ListsCache = null;   // 已加载的清单列表（避免重复请求）
  let _khFolders        = [];     // 知识库文件夹列表（_fetchAllLists 时同步拉取）
  let _allProjects      = [];     // 项目列表（_fetchAllLists 时同步拉取）

  // 面板2 设置 & 搜索
  const _P2_SETTINGS_LS = 'wb:p2-settings';
  let _p2Settings = (() => {
    try {
      const s = JSON.parse(localStorage.getItem(_lsk(_P2_SETTINGS_LS)) || '{}');
      return { hideSecs: s.hideSecs || [], filterProjects: s.filterProjects || [] };
    } catch { return { hideSecs: [], filterProjects: [] }; }
  })();
  let _p2SearchQuery = '';
  function _saveP2Settings() {
    localStorage.setItem(_lsk(_P2_SETTINGS_LS), JSON.stringify(_p2Settings));
  }

  // 收藏文件夹状态
  const _FAV_FOLDERS_LS = 'wb:p2-fav-folders';
  let _favFolders = [];       // [{id: string, name: string}]
  let _favFolderItems = {};   // {folderId: [gid, ...]}
  function _loadFavFolders() {
    try {
      const d = JSON.parse(localStorage.getItem(_lsk(_FAV_FOLDERS_LS)) || '{}');
      _favFolders = Array.isArray(d.folders) ? d.folders : [];
      _favFolderItems = (d.items && typeof d.items === 'object') ? d.items : {};
    } catch { _favFolders = []; _favFolderItems = {}; }
  }
  function _saveFavFolders() {
    localStorage.setItem(_lsk(_FAV_FOLDERS_LS), JSON.stringify({ folders: _favFolders, items: _favFolderItems }));
  }
  _loadFavFolders();

  let _midMaximized   = false;    // 中列是否最大化
  let _midMaxLastTap  = 0;        // 上次按 3/4 的时间戳（双击检测）

  // 面板3 内层 tabs：[{id:'default',title:'我的主业务'} | {id:listGid, title, itemType, listGid}]
  let _p3Tabs        = [{ id: 'default', title: '我的主业务' }];
  let _p3ActiveTabIdx = 0;
  let _p3Tls         = null;   // 当前激活的 TreeListShell 实例
  let _p3TlsKey      = null;   // itemType:listGid，用于判断是否需要重建

  // 详情条状态（两面板各自独立）
  let _p1DetailOpen = false;   // 面板1详情条是否展开
  let _p1DetailItem = null;    // 面板1当前选中条目
  let _p3DetailOpen = false;   // 面板3详情条是否展开
  let _p3DetailItem = null;    // 面板3当前选中条目

  // 面板1 设置
  const _P1_SETTINGS_LS = 'wb:p1-settings';
  let _p1Settings = (() => {
    try {
      return JSON.parse(localStorage.getItem(_lsk(_P1_SETTINGS_LS)) || 'null') || {
        sources: ['task', 'issue', 'feishu'], listFilter: {}, groupBy: 'date', sortBy: 'scheduled_date',
        statusFilter: ['pending', 'progress', 'done', 'closed'],
      };
    } catch { return { sources: ['task', 'issue', 'feishu'], listFilter: {}, groupBy: 'date', sortBy: 'scheduled_date',
        statusFilter: ['pending', 'progress', 'done', 'closed'] }; }
  })();
  if (!_p1Settings.listFilter) _p1Settings.listFilter = {}; // 旧存档兼容
  // 迁移：旧存档没有 feishu 时默认补入（feishu 以前总是显示）
  if (!_p1Settings.sources.includes('feishu')) _p1Settings.sources.push('feishu');
  let _p1GroupOpen = { '未安排': false };   // { groupKey: bool } 分组折叠状态，未安排默认收起
  let _p1ReloadTimer = 0;  // debounce timer for settings-change reload

  // 面板1 列定义（所有 itemType）
  const WB_P1_COLS_TASK = [
    { key: 'title',          label: '标题',   defaultOn: true  },
    { key: 'status',         label: '状态',   defaultOn: true,  width: 72 },
    { key: 'priority',       label: '优先级', defaultOn: true,  width: 60 },
    { key: 'due_date',       label: '截止',   defaultOn: true,  width: 80 },
    { key: 'owner',          label: '负责人', defaultOn: false, width: 70 },
    { key: 'project_name',   label: '项目',   defaultOn: false, width: 90 },
    { key: 'scheduled_date', label: '计划日', defaultOn: false, width: 80 },
    { key: 'created_at',     label: '创建',   defaultOn: false, width: 80 },
  ];
  const WB_P1_COLS_ISSUE = [
    { key: 'title',        label: '标题',   defaultOn: true  },
    { key: 'status',       label: '状态',   defaultOn: true,  width: 72 },
    { key: 'severity',     label: '严重度', defaultOn: true,  width: 60 },
    { key: 'category',     label: '分类',   defaultOn: false, width: 80 },
    { key: 'owner',        label: '负责人', defaultOn: false, width: 70 },
    { key: 'project_name', label: '项目',   defaultOn: false, width: 90 },
    { key: 'created_at',   label: '创建',   defaultOn: false, width: 80 },
  ];
  const WB_P1_COLS_BOP = [
    { key: 'title',        label: '标题',    defaultOn: true  },
    { key: 'node_type',    label: '节点类型', defaultOn: true,  width: 80 },
    { key: 'vpps',         label: 'VPPS',    defaultOn: true,  width: 90 },
    { key: 'vpps_desc',    label: 'VPPS描述', defaultOn: false, width: 120 },
    { key: 'ai00_level',   label: 'L',       defaultOn: false, width: 30 },
    { key: 'level',        label: 'TC级',    defaultOn: false, width: 50 },
    { key: 'link_type',    label: '关联类型', defaultOn: false, width: 80 },
    { key: 'tracking_link_count', label: '追踪', defaultOn: false, width: 40 },
  ];
  const WB_P1_COLS_PBOM = [
    { key: 'name',         label: '名称',   defaultOn: true  },
    { key: 'part_no',      label: '零件号', defaultOn: true,  width: 100 },
    { key: 'vpps',         label: 'VPPS',   defaultOn: true,  width: 90  },
    { key: 'quantity',     label: '数量',   defaultOn: false, width: 50  },
    { key: 'bom_row',      label: 'BOM行',  defaultOn: false, width: 70  },
    { key: 'level',        label: '层级',   defaultOn: false, width: 50  },
    { key: 'unit',         label: '单位',   defaultOn: false, width: 50  },
  ];
  const WB_P1_COLS_KNOWLEDGE = [
    { key: 'title',      label: '标题',   defaultOn: true  },
    { key: 'category',   label: '分类',   defaultOn: true,  width: 70 },
    { key: 'status',     label: '状态',   defaultOn: true,  width: 60 },
    { key: 'tags',       label: '标签',   defaultOn: false, width: 90 },
    { key: 'source',     label: '来源',   defaultOn: false, width: 70 },
    { key: 'updated_at', label: '更新',   defaultOn: false, width: 80 },
    { key: 'created_at', label: '创建',   defaultOn: false, width: 80 },
  ];
  const WB_P1_COLS_RULE = [
    { key: 'title',      label: '标题',   defaultOn: true  },
    { key: 'status',     label: '状态',   defaultOn: true,  width: 60 },
    { key: 'category',   label: '分类',   defaultOn: true,  width: 70 },
    { key: 'priority',   label: '优先级', defaultOn: false, width: 60 },
    { key: 'severity',   label: '严重度', defaultOn: false, width: 60 },
    { key: 'updated_at', label: '更新',   defaultOn: false, width: 80 },
  ];
  const WB_P1_COLS_MAP = {
    task:        WB_P1_COLS_TASK,
    issue:       WB_P1_COLS_ISSUE,
    bop_version: WB_P1_COLS_BOP,
    pbom:        WB_P1_COLS_PBOM,
    knowledge:   WB_P1_COLS_KNOWLEDGE,
    rule:        WB_P1_COLS_RULE,
  };
  const WB_P1_PARENT_MAP = {
    task:        'parent_task_gid',
    issue:       null,
    bop_version: 'parent_gid',
    pbom:        'parent_gid',
    knowledge:   null,
    rule:        null,
  };
  const WB_P1_GROUP_MAP = {
    task:        'status',
    issue:       'status',
    bop_version: 'node_type',
    pbom:        null,
    knowledge:   'category',
    rule:        'category',
  };
  const WB_P1_API_MAP = {
    task:        (listGid) => `/api/tasks?list_gid=${listGid}&limit=200`,
    issue:       (listGid) => `/api/issues?list_gid=${listGid}&limit=200`,
    bop_version: (listGid) => `/api/bop/versions/${listGid}/entries?limit=200`,
    pbom:        (listGid) => `/api/ebom/snapshots/${listGid}/parts`,
    knowledge:   (listGid) => `/api/knowledge?list_gid=${listGid}&limit=200`,
    rule:        (listGid) => `/api/rules?list_gid=${listGid}&limit=200`,
  };

  function _loadTreeOpen() {
    try { return JSON.parse(localStorage.getItem(_lsk('wb:p2-tree-open')) || '{}'); }
    catch { return {}; }
  }
  function _saveTreeOpen() {
    localStorage.setItem(_lsk('wb:p2-tree-open'), JSON.stringify(_treeOpen));
  }

  function _loadRecentFiles() {
    try { return JSON.parse(localStorage.getItem(_lsk('wb:p2-recent')) || '[]'); }
    catch { return []; }
  }

  function _addRecentFile(list) {
    const entry = { gid: list.gid, name: list.name || list.title || '', item_type: list.item_type || 'task' };
    _recentFiles = _recentFiles.filter(f => f.gid !== entry.gid);
    _recentFiles.unshift(entry);
    if (_recentFiles.length > 5) _recentFiles = _recentFiles.slice(0, 5);
    localStorage.setItem(_lsk('wb:p2-recent'), JSON.stringify(_recentFiles));
    if (_treeSections) _renderP2TreeSections(_treeSections);
  }

  // 今日待办列宽（从 localStorage 恢复）
  (function _initTodayWidth() {
    try {
      const v = +localStorage.getItem(_lsk('wb:today-w'));
      if (v >= 60 && v <= 320) document.documentElement.style.setProperty('--wb-today-w', v + 'px');
    } catch {}
  })();

  function _getActiveTabMode() {
    return { type: 'today' };   // 面板1 现在始终为今日待办模式
  }

  // ── 面板2 内容树导航 ───────────────────────────────────────────────────────

  function _renderP2Tree() {
    const treeEl = document.getElementById('wb-p2-tree');
    if (!treeEl) return;
    treeEl.innerHTML = '<div class="wb-loading">加载中…</div>';

    const fn = _cf();
    if (!fn) { treeEl.innerHTML = '<div class="wb-empty">请先登录</div>'; return; }

    _fetchAllLists().then(allLists => {
      _panel1ListsCache = allLists;
      const uid = _currentUser?.gid;

      // 读取 mf:favorites（我的文件页收藏）
      let mfFavGids = new Set();
      try { mfFavGids = new Set(JSON.parse(localStorage.getItem(_lsk('mf:favorites')) || '[]').map(f => f.gid)); } catch (_) {}

      // 关注的文件 gid 集合（来自 Panel5 数据）
      const followedGids = new Set((_panelData[4] || []).map(f => f.item_gid));

      // ── 收藏的文件 = 我的文件 + 关注的文件 + 明确收藏的文件 ──
      const favMap = new Map();
      allLists.forEach(l => {
        const isOwn      = (l.owner_gid && l.owner_gid === uid) || (l.created_by && l.created_by === uid);
        const isFollowed = followedGids.has(l.gid);
        const isFav      = mfFavGids.has(l.gid);
        if (isOwn || isFollowed || isFav) favMap.set(l.gid, l);
      });
      const favList = [...favMap.values()];

      // ── 公共文件（BOP/知识文档默认公共）──
      const domainOf = l => {
        const t = l.item_type || 'task';
        if (t === 'project')                                          return 'project';
        if (t === 'task' || t === 'issue')                            return 'task_issue';
        if (t === 'bop_version' || t === 'pbom')                     return 'craft';
        if (t === 'knowledge' || t === 'knowledge_doc' || t === 'rule') return 'knowledge';
        return 'other';
      };

      // 项目文件：来自项目管理 app 的项目（后端已按权限过滤）
      const pubProject = _allProjects.map(p => ({
        ...p,
        name: p.name || p.project_code || p.gid,
        item_type: 'project',
      }));

      const isPublicScope = l => {
        const d = domainOf(l);
        if (d === 'craft' || d === 'knowledge') return true;
        return l.share_scope === 'org' || l.share_scope === 'team' || l.share_scope === 'global';
      };
      const publicLists = allLists.filter(l => isPublicScope(l) && !favMap.has(l.gid));
      const pubKnowledge = publicLists.filter(l => domainOf(l) === 'knowledge');

      // 工艺文件按 project_gid 分组，挂到对应项目下（不再单独显示工艺分类）
      const pubCraftAll = publicLists.filter(l => domainOf(l) === 'craft');
      const craftByProject = {};
      pubCraftAll.forEach(c => {
        const pgid = c.project_gid || '__none__';
        if (!craftByProject[pgid]) craftByProject[pgid] = [];
        craftByProject[pgid].push(c);
      });

      // 所有清单按 project_gid 分组（任务/问题/工艺等均包括）
      const listsByProject = {};
      allLists
        .filter(l => l.project_gid && domainOf(l) !== 'project')
        .forEach(l => {
          if (!listsByProject[l.project_gid]) listsByProject[l.project_gid] = [];
          listsByProject[l.project_gid].push(l);
        });

      const _hp = window.parent?._hasTabPerm;
      const canCreate = !!(typeof _hp === 'function' &&
        (_hp('knowledge_admin') || _hp('system.user.manage')));

      _renderP2TreeSections([
        { key: 'favorites', label: '收藏的文件', items: favList, canCreate },
        {
          key: 'public', label: '公共文件', items: [], canCreate,
          subs: [
            { key: 'pub_project',   label: '项目', items: pubProject, craftByProject, craftItems: pubCraftAll, listsByProject },
            { key: 'pub_knowledge', label: '知识', items: pubKnowledge },
          ],
        },
      ]);
    }).catch(() => {
      const t = document.getElementById('wb-p2-tree');
      if (t) t.innerHTML = '<div class="wb-empty">加载失败</div>';
    });
  }

  function _renderP2TreeSections(sections) {
    _treeSections = sections;
    const treeEl = document.getElementById('wb-p2-tree');
    if (!treeEl) return;

    // 最近文件置顶
    const allSections = _recentFiles.length
      ? [{ key: 'recent', label: '最近文件', items: _recentFiles, canCreate: false }, ...sections]
      : sections;

    // ── 大标题过滤 ────────────────────────────────────────────────────────
    const _hideSecs = _p2Settings.hideSecs || [];
    let visibleSections = allSections.map(sec => {
      if (sec.subs) {
        // 对 public 型：过滤子分区
        const filtSubs = sec.subs.filter(sub => !_hideSecs.includes(sub.key));
        if (!filtSubs.length) return null;
        return { ...sec, subs: filtSubs };
      }
      return _hideSecs.includes(sec.key) ? null : sec;
    }).filter(Boolean);

    // ── 项目筛选 ──────────────────────────────────────────────────────────
    const _filterProjs = _p2Settings.filterProjects || [];
    if (_filterProjs.length) {
      visibleSections = visibleSections.map(sec => {
        if (!sec.subs) return sec;
        return {
          ...sec,
          subs: sec.subs.map(sub => {
            if (sub.key !== 'pub_project') return sub;
            const filtItems = sub.items.filter(p => _filterProjs.includes(p.gid));
            const filtCraft = {};
            filtItems.forEach(p => { if (sub.craftByProject?.[p.gid]) filtCraft[p.gid] = sub.craftByProject[p.gid]; });
            const filtCraftItems = (sub.craftItems || []).filter(c => _filterProjs.includes(c.project_gid));
            const filtLists = {};
            filtItems.forEach(p => { if (sub.listsByProject?.[p.gid]) filtLists[p.gid] = sub.listsByProject[p.gid]; });
            return { ...sub, items: filtItems, craftByProject: filtCraft, craftItems: filtCraftItems, listsByProject: filtLists };
          }),
        };
      });
    }

    const TYPE_ICON = {
      task:        `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="2" width="12" height="12" rx="2"/><polyline points="5,8 7,10 11,6" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
      issue:       `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6"/><line x1="8" y1="5" x2="8" y2="9" stroke-linecap="round"/><circle cx="8" cy="11.5" r=".6" fill="currentColor"/></svg>`,
      knowledge:     `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 2h8a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z"/><line x1="5" y1="6" x2="11" y2="6" stroke-linecap="round"/><line x1="5" y1="9" x2="9" y2="9" stroke-linecap="round"/></svg>`,
      knowledge_doc: `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 2h6l3 3v9a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z"/><polyline points="10,2 10,5 13,5" stroke-linejoin="round"/></svg>`,
      rule:        `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><polygon points="8,2 14,5 14,11 8,14 2,11 2,5"/><line x1="8" y1="6" x2="8" y2="9" stroke-linecap="round"/><circle cx="8" cy="11" r=".6" fill="currentColor"/></svg>`,
      bop_version: `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="7" width="4" height="7"/><rect x="6" y="4" width="4" height="10"/><rect x="10" y="1" width="4" height="13"/></svg>`,
      pbom:        `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 3h12M2 8h8M2 13h5" stroke-linecap="round"/><circle cx="13" cy="11" r="2.5"/><line x1="13" y1="8.5" x2="13" y2="9" stroke-linecap="round"/></svg>`,
      project:     `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="1" y="5" width="14" height="9" rx="1"/><path d="M4 5V4a2 2 0 014 0v1" stroke-linecap="round"/></svg>`,
      _today:      `<svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1l1.8 4.4H15l-4.3 3.1 1.6 4.9L8 10.7l-4.3 2.7 1.6-4.9L1 5.4h5.2z"/></svg>`,
    };
    const _addSvg        = `<svg width="9" height="9" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="2" x2="8" y2="14"/><line x1="2" y1="8" x2="14" y2="8"/></svg>`;
    const _arrowD        = `<svg width="8" height="8" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1,3 5,7 9,3"/></svg>`;
    const _arrowR        = `<svg width="8" height="8" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3,1 7,5 3,9"/></svg>`;
    const _folderSvg     = `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 4h4l1.5 2H14a1 1 0 011 1v6a1 1 0 01-1 1H2a1 1 0 01-1-1V5a1 1 0 011-1z"/></svg>`;
    const _folderOpenSvg = `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 4h4l1.5 2H14a1 1 0 011 1v6a1 1 0 01-1 1H2a1 1 0 01-1-1V5a1 1 0 011-1z"/><line x1="1" y1="9" x2="15" y2="9" stroke-dasharray="2 1"/></svg>`;
    const _folderPlusSvg = `<svg width="9" height="9" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M2 4h4l1.5 2H14a1 1 0 011 1v6a1 1 0 01-1 1H2a1 1 0 01-1-1V5a1 1 0 011-1z"/><line x1="10" y1="8" x2="10" y2="13"/><line x1="7.5" y1="10.5" x2="12.5" y2="10.5"/></svg>`;

    // 递归构建知识文件夹树 HTML
    const _khDocs = allSections.flatMap(s =>
      [...(s.items || []), ...(s.subs || []).flatMap(sub => sub.items || [])]
    ).filter(i => i.item_type === 'knowledge_doc');

    function _renderKhTree(parentGid, depth) {
      const pad = 24 + depth * 12;
      let h = '';
      const childFolders = _khFolders.filter(f => (f.parent_gid || null) === parentGid);
      const childDocs    = _khDocs.filter(d => (d.folder_gid || null) === parentGid);
      for (const f of childFolders) {
        const key    = 'kf:' + f.gid;
        const isOpen = _treeOpen[key] === true;
        h += `<div class="wb-p1-tree-folder" data-kf-gid="${_esc(f.gid)}" style="padding-left:${pad}px">
          <span class="wb-p1-tree-sec-arrow">${isOpen ? _arrowD : _arrowR}</span>
          <span class="wb-p1-tree-item-icon">${isOpen ? _folderOpenSvg : _folderSvg}</span>
          <span class="wb-p1-tree-item-name">${_esc(f.name || '未命名文件夹')}</span>
        </div>`;
        if (isOpen) h += `<div class="wb-p1-tree-folder-body">${_renderKhTree(f.gid, depth + 1)}</div>`;
      }
      for (const doc of childDocs) {
        h += `<div class="wb-p1-tree-item" data-list-gid="${_esc(doc.gid)}" style="padding-left:${pad}px" title="${_esc(doc.title || '')}">
          <span class="wb-p1-tree-item-icon">${TYPE_ICON['knowledge_doc'] || ''}</span>
          <span class="wb-p1-tree-item-name">${_esc(doc.title || doc.name || '')}</span>
        </div>`;
      }
      if (!h) h = `<div class="wb-p1-tree-empty" style="padding-left:${pad}px">暂无文件</div>`;
      return h;
    }

    // 渲染单个条目行
    const _vsBadge = (item) => window.VisibilitySelector
      ? VisibilitySelector.renderBadge(item.visibility || item.scope_type || 'team')
      : '';
    const _itemRow = item =>
      `<div class="wb-p1-tree-item" data-list-gid="${_esc(item.gid)}" title="${_esc(item.name || item.title || '')}">
        ${_vsBadge(item)}<span class="wb-p1-tree-item-icon">${TYPE_ICON[item.item_type || 'task'] || TYPE_ICON.task}</span>
        <span class="wb-p1-tree-item-name">${_esc(item.name || item.title || '')}</span>
      </div>`;

    // 个人知识库文件夹树（与 _renderKhTree 结构相同，但数据源用 _khPersonalFolders/_khPersonalDocs）
    function _renderKhPersonalTree(parentGid, depth) {
      const pad = 24 + depth * 12;
      let h = '';
      const childFolders = _khPersonalFolders.filter(f => (f.parent_gid || null) === parentGid);
      const childDocs    = _khPersonalDocs.filter(d => (d.folder_gid || null) === parentGid);
      for (const f of childFolders) {
        const key    = 'kfp:' + f.gid;
        const isOpen = _treeOpen[key] === true;
        h += `<div class="wb-p1-tree-folder" data-kf-gid="${_esc(f.gid)}" style="padding-left:${pad}px">
          <span class="wb-p1-tree-sec-arrow">${isOpen ? _arrowD : _arrowR}</span>
          <span class="wb-p1-tree-item-icon">${isOpen ? _folderOpenSvg : _folderSvg}</span>
          <span class="wb-p1-tree-item-name">${_esc(f.name || '未命名文件夹')}</span>
        </div>`;
        if (isOpen) h += _renderKhPersonalTree(f.gid, depth + 1);
      }
      for (const d of childDocs) {
        h += `<div class="wb-p1-tree-item" data-list-gid="${_esc(d.gid)}" style="padding-left:${pad + 12}px" title="${_esc(d.name || '')}">
          <span class="wb-p1-tree-item-icon">${TYPE_ICON.knowledge_doc || TYPE_ICON.task}</span>
          <span class="wb-p1-tree-item-name">${_esc(d.name || '')}</span>
        </div>`;
      }
      return h;
    }

    // 渲染项目树（每个项目下嵌套所有关联清单）
    function _renderProjectTree(projects, listsByProject) {
      const rows = [];
      for (const p of projects) {
        const children = listsByProject[p.gid] || [];
        const key      = 'pj:' + p.gid;
        const isOpen   = _treeOpen[key] === true;
        const arrowHtml = children.length
          ? `<span class="wb-p1-tree-sec-arrow">${isOpen ? _arrowD : _arrowR}</span>`
          : `<span style="display:inline-block;width:12px;flex-shrink:0"></span>`;
        let h = `<div class="wb-p1-tree-proj-hdr" data-proj-key="${_esc(key)}">`;
        h += arrowHtml;
        h += `<span class="wb-p1-tree-item-icon">${TYPE_ICON.project}</span>`;
        h += `<span class="wb-p1-tree-item-name">${_esc(p.name || '')}</span>`;
        h += `</div>`;
        if (children.length && isOpen) {
          h += `<div class="wb-p1-tree-proj-children">`;
          h += children.map(c =>
            `<div class="wb-p1-tree-item" data-list-gid="${_esc(c.gid)}" style="padding-left:36px" title="${_esc(c.name || '')}">
              ${_vsBadge(c)}<span class="wb-p1-tree-item-icon">${TYPE_ICON[c.item_type || 'task'] || TYPE_ICON.task}</span>
              <span class="wb-p1-tree-item-name">${_esc(c.name || '')}</span>
            </div>`
          ).join('');
          h += `</div>`;
        }
        rows.push(`<div class="wb-p1-tree-proj-wrap">${h}</div>`);
      }
      if (!rows.length) return '<div class="wb-p1-tree-empty">暂无项目</div>';
      return rows.join('');
    }

    let html = '';

    visibleSections.forEach(sec => {
      const isOpen = _treeOpen[sec.key] !== false;

      // 计算展示数量（含子区段总和）
      const totalCount = sec.subs
        ? sec.subs.reduce((s, sub) => s + sub.items.length, 0)
        : sec.items.length;

      // 内层内容（子区段 or 平铺条目）
      let innerHtml = '';
      if (isOpen) {
        if (sec.subs) {
          // 有子区段：按 项目 / 工艺 / 知识 分组渲染
          sec.subs.forEach(sub => {
            const subOpen = _treeOpen[sub.key] === true;
            // 知识子区段：渲染公共文件夹树 + 个人文件夹
            const subBodyHtml = sub.key === 'pub_knowledge'
              ? (() => {
                  // 公共文件夹树
                  const pubHtml = _renderKhTree(null, 0);
                  // 个人知识库子折叠区
                  const persKey = 'kh_personal';
                  const persOpen = _treeOpen[persKey] !== false;
                  const persBodyHtml = _renderKhPersonalTree(null, 0);
                  const persCount = (_khPersonalFolders.length + _khPersonalDocs.length) || '';
                  const persSection = `
                    <div class="wb-p1-tree-subsec" style="margin-top:2px">
                      <div class="wb-p1-tree-subsec-hdr" data-subsec="${persKey}">
                        <span class="wb-p1-tree-sec-arrow">${persOpen ? _arrowD : _arrowR}</span>
                        <span class="wb-p1-tree-subsec-label">个人</span>
                        ${persCount ? `<span class="wb-p1-tree-count">${persCount}</span>` : ''}
                      </div>
                      ${persOpen ? `<div class="wb-p1-tree-subsec-body">${persBodyHtml || '<div class="wb-p1-tree-empty">暂无个人文档</div>'}</div>` : ''}
                    </div>`;
                  return pubHtml + persSection;
                })()
              : sub.key === 'pub_project'
                ? _renderProjectTree(sub.items, sub.listsByProject || {})
                : (sub.items.length === 0
                    ? '<div class="wb-p1-tree-empty">暂无文件</div>'
                    : sub.items.map(_itemRow).join(''));
            const subCount = sub.key === 'pub_knowledge'
              ? (_khFolders.length + _khPersonalFolders.length + sub.items.length + _khPersonalDocs.length) || ''
              : sub.key === 'pub_project'
                ? sub.items.length || ''
                : (sub.items.length || '');
            innerHtml += `<div class="wb-p1-tree-subsec">
              <div class="wb-p1-tree-subsec-hdr" data-subsec="${_esc(sub.key)}">
                <span class="wb-p1-tree-sec-arrow">${subOpen ? _arrowD : _arrowR}</span>
                <span class="wb-p1-tree-subsec-label">${_esc(sub.label)}</span>
                ${subCount ? `<span class="wb-p1-tree-count">${subCount}</span>` : ''}
              </div>
              ${subOpen ? `<div class="wb-p1-tree-subsec-body">${subBodyHtml}</div>` : ''}
            </div>`;
          });
        } else if (sec.key === 'favorites') {
          // 收藏文件夹 + 未分组条目
          const favItemByGid = {};
          sec.items.forEach(i => { favItemByGid[i.gid] = i; });
          let fh = '';
          _favFolders.forEach(folder => {
            const fKey = 'ff:' + folder.id;
            const fOpen = _treeOpen[fKey] === true;
            const childGids = _favFolderItems[folder.id] || [];
            const childItems = childGids.map(g => favItemByGid[g]).filter(Boolean);
            fh += `<div class="wb-fav-folder-row" data-fav-folder-id="${_esc(folder.id)}">
              <span class="wb-p1-tree-sec-arrow">${fOpen ? _arrowD : _arrowR}</span>
              <span class="wb-p1-tree-item-icon">${fOpen ? _folderOpenSvg : _folderSvg}</span>
              <span class="wb-fav-folder-name">${_esc(folder.name || '未命名文件夹')}</span>
              ${childItems.length ? `<span class="wb-p1-tree-count">${childItems.length}</span>` : ''}
            </div>`;
            if (fOpen) {
              if (childItems.length) {
                fh += `<div class="wb-fav-folder-body">`;
                fh += childItems.map(i =>
                  `<div class="wb-p1-tree-item wb-fav-item" data-list-gid="${_esc(i.gid)}" data-fav-gid="${_esc(i.gid)}" data-fav-folder="${_esc(folder.id)}" style="padding-left:28px" title="${_esc(i.name || i.title || '')}">
                    <span class="wb-p1-tree-item-icon">${TYPE_ICON[i.item_type || 'task'] || TYPE_ICON.task}</span>
                    <span class="wb-p1-tree-item-name">${_esc(i.name || i.title || '')}</span>
                  </div>`
                ).join('');
                fh += `</div>`;
              } else {
                fh += `<div class="wb-p1-tree-empty" style="padding-left:28px">文件夹为空</div>`;
              }
            }
          });
          // 未归入文件夹的条目
          const allFolderGids = new Set(Object.values(_favFolderItems).flat());
          const rootItems = sec.items.filter(i => !allFolderGids.has(i.gid));
          fh += rootItems.map(i =>
            `<div class="wb-p1-tree-item wb-fav-item" data-list-gid="${_esc(i.gid)}" data-fav-gid="${_esc(i.gid)}" data-fav-folder="" title="${_esc(i.name || i.title || '')}">
              <span class="wb-p1-tree-item-icon">${TYPE_ICON[i.item_type || 'task'] || TYPE_ICON.task}</span>
              <span class="wb-p1-tree-item-name">${_esc(i.name || i.title || '')}</span>
            </div>`
          ).join('');
          innerHtml = fh || '<div class="wb-p1-tree-empty">暂无收藏文件</div>';
        } else {
          innerHtml = sec.items.length === 0
            ? '<div class="wb-p1-tree-empty">暂无文件</div>'
            : sec.items.map(_itemRow).join('');
        }
      }

      html += `<div class="wb-p1-tree-section">
        <div class="wb-p1-tree-sec-hdr" data-sec="${_esc(sec.key)}">
          <span class="wb-p1-tree-sec-arrow">${isOpen ? _arrowD : _arrowR}</span>
          <span class="wb-p1-tree-sec-label">${_esc(sec.label)}</span>
          ${totalCount ? `<span class="wb-p1-tree-count">${totalCount}</span>` : ''}
          ${sec.canCreate ? `<button class="wb-p1-tree-add" data-create-sec="${_esc(sec.key)}" title="新建文件">${_addSvg}</button>` : ''}
          ${sec.key === 'favorites' ? `<button class="wb-p1-tree-add wb-fav-add-folder" data-fav-create-folder="1" title="新建文件夹">${_folderPlusSvg}</button>` : ''}
        </div>
        ${isOpen ? `<div class="wb-p1-tree-items">${innerHtml}</div>` : ''}
      </div>`;
    });

    // ── 搜索模式：覆盖正常渲染 ────────────────────────────────────────────
    const _q = _p2SearchQuery.trim().toLowerCase();
    if (_q) {
      const matched = [];
      allSections.forEach(sec => {
        if (sec.subs) {
          sec.subs.forEach(sub => {
            (sub.items || []).forEach(i => { if ((i.name || i.title || '').toLowerCase().includes(_q)) matched.push({ ...i, _tag: sub.label }); });
            (sub.craftItems || []).forEach(i => { if ((i.name || i.title || '').toLowerCase().includes(_q)) matched.push({ ...i, _tag: sub.label }); });
          });
        } else {
          (sec.items || []).forEach(i => { if ((i.name || i.title || '').toLowerCase().includes(_q)) matched.push({ ...i, _tag: sec.label }); });
        }
      });
      _khDocs.forEach(d => { if ((d.title || d.name || '').toLowerCase().includes(_q) && !matched.some(m => m.gid === d.gid)) matched.push({ ...d, _tag: '知识' }); });
      treeEl.innerHTML = matched.length
        ? matched.map(i => `<div class="wb-p1-tree-item wb-p2-sr-row" data-list-gid="${_esc(i.gid)}" title="${_esc(i.name || i.title || '')}">
            <span class="wb-p1-tree-item-icon">${TYPE_ICON[i.item_type || 'task'] || ''}</span>
            <span class="wb-p1-tree-item-name">${_esc(i.name || i.title || '')}</span>
            <span class="wb-p2-sr-tag">${_esc(i._tag)}</span>
          </div>`).join('')
        : '<div class="wb-p1-tree-empty" style="padding:14px 10px">无匹配文件</div>';
      const srMap = {};
      matched.forEach(i => { srMap[i.gid] = i; });
      treeEl.querySelectorAll('.wb-p1-tree-item').forEach(el => {
        el.addEventListener('click', () => {
          const l = srMap[el.dataset.listGid];
          if (l) _openListInP3(l);
          treeEl.querySelectorAll('.wb-p1-tree-item').forEach(x => x.classList.remove('active'));
          el.classList.add('active');
        });
        el.addEventListener('contextmenu', e => {
          e.preventDefault();
          const l = srMap[el.dataset.listGid];
          if (l) _showListItemCtxMenu(e, l);
        });
      });
    }

    treeEl.innerHTML = html;

    // Section header — 展开/折叠
    treeEl.querySelectorAll('.wb-p1-tree-sec-hdr').forEach(hdr => {
      hdr.addEventListener('click', e => {
        if (e.target.closest('.wb-p1-tree-add')) return;
        const key = hdr.dataset.sec;
        _treeOpen[key] = !(_treeOpen[key] !== false);
        _saveTreeOpen();
        _renderP2TreeSections(_treeSections);
      });
    });

    // 子区段 header — 展开/折叠
    treeEl.querySelectorAll('.wb-p1-tree-subsec-hdr').forEach(hdr => {
      hdr.addEventListener('click', () => {
        const key = hdr.dataset.subsec;
        _treeOpen[key] = _treeOpen[key] !== true;
        _saveTreeOpen();
        _renderP2TreeSections(_treeSections);
      });
    });

    // 知识文件夹 — 展开/折叠
    treeEl.querySelectorAll('.wb-p1-tree-folder').forEach(el => {
      el.addEventListener('click', () => {
        const key = 'kf:' + el.dataset.kfGid;
        _treeOpen[key] = _treeOpen[key] !== true;
        _saveTreeOpen();
        _renderP2TreeSections(_treeSections);
      });
    });

    // 项目节点 — 展开/折叠子工艺文件（整行可点击）
    treeEl.querySelectorAll('.wb-p1-tree-proj-hdr').forEach(el => {
      el.addEventListener('click', () => {
        const key = el.dataset.projKey;
        _treeOpen[key] = _treeOpen[key] !== true;
        _saveTreeOpen();
        _renderP2TreeSections(_treeSections);
      });
    });

    // 创建清单
    treeEl.querySelectorAll('.wb-p1-tree-add').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        _createList(btn.dataset.createSec);
      });
    });

    // 清单条目点击 → 在面板3打开
    const listMap = {};
    allSections.forEach(s => {
      (s.items || []).forEach(l => { listMap[l.gid] = l; });
      (s.subs  || []).forEach(sub => (sub.items || []).forEach(l => { listMap[l.gid] = l; }));
    });
    // 知识文档也加入 listMap（由文件夹树动态渲染，不在 allSections.items 中）
    _khDocs.forEach(d => { listMap[d.gid] = d; });
    _khPersonalDocs.forEach(d => { listMap[d.gid] = d; });
    // 项目下挂载的所有清单加入 listMap（嵌套在项目行下渲染，不在 sub.items 中）
    allSections.forEach(s => (s.subs || []).forEach(sub => {
      Object.values(sub.listsByProject || {}).forEach(arr => arr.forEach(l => { listMap[l.gid] = l; }));
      (sub.craftItems || []).forEach(c => { listMap[c.gid] = c; }); // 兼容旧字段
    }));
    treeEl.querySelectorAll('.wb-p1-tree-item').forEach(el => {
      el.addEventListener('click', () => {
        const l = listMap[el.dataset.listGid];
        if (l) _openListInP3(l);
        treeEl.querySelectorAll('.wb-p1-tree-item').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
      });
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        const l = listMap[el.dataset.listGid];
        if (l) _showListItemCtxMenu(e, l);
      });
    });

    // 收藏文件夹 — 展开/折叠
    treeEl.querySelectorAll('.wb-fav-folder-row').forEach(el => {
      el.addEventListener('click', e => {
        if (e.target.closest('[data-fav-create-folder]')) return;
        const fid = el.dataset.favFolderId;
        const key = 'ff:' + fid;
        _treeOpen[key] = _treeOpen[key] !== true;
        _saveTreeOpen();
        _renderP2TreeSections(_treeSections);
      });
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        _showFavFolderCtxMenu(e, el.dataset.favFolderId);
      });
    });

    // 收藏文件夹 — 新建
    treeEl.querySelectorAll('[data-fav-create-folder]').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        const name = await _promptText('新建文件夹', '');
        if (!name) return;
        const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
        _favFolders.push({ id, name });
        _saveFavFolders();
        _renderP2TreeSections(_treeSections);
      });
    });

    // 收藏条目 — 右键
    treeEl.querySelectorAll('.wb-fav-item').forEach(el => {
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        _showFavItemCtxMenu(e, el.dataset.favGid, el.dataset.favFolder);
      });
    });
  }

  // ── 面板3 内层 tabs（清单条目视图）───────────────────────────────────────

  function _openListInP3(listItem) {
    _addRecentFile(listItem);
    const existIdx = _p3Tabs.findIndex(t => t.id === listItem.gid);
    if (existIdx >= 0) {
      _switchP3Tab(existIdx);
    } else {
      _p3Tabs.push({
        id:       listItem.gid,
        title:    listItem.name || listItem.title || '',
        itemType: listItem.item_type || 'task',
        listGid:  listItem.gid,
      });
      _switchP3Tab(_p3Tabs.length - 1);
    }
    // 若面板3未显示，自动打开
    if (!_vis.center) {
      _vis.center = true;
      _saveVis();
      _switchCenterTab(3);
      _updateLayout();
    } else if (_centerTab !== 3) {
      _switchCenterTab(3);
    }
  }

  function _openDocInViewer(doc) {
    const tabId = 'fsh_doc:' + doc.url;
    const existIdx = _p3Tabs.findIndex(t => t.id === tabId);
    if (existIdx >= 0) {
      _switchP3Tab(existIdx);
    } else {
      _p3Tabs.push({ id: tabId, title: doc.title || '飞书文档', itemType: 'feishu_doc', url: doc.url });
      _switchP3Tab(_p3Tabs.length - 1);
    }
    if (!_vis.center) { _vis.center = true; _saveVis(); _switchCenterTab(3); _updateLayout(); }
    _focusPanel(3);
  }

  function _renderP3Tabs() {
    const el = document.getElementById('wb-p3-tabs');
    if (!el) return;

    // 只显示动态列表 tab；默认 tab 时隐藏 tab 栏
    if (_p3Tabs.length <= 1 && _p3Tabs[0]?.id === 'default') {
      el.classList.add('hidden');
      el.innerHTML = '';
      return;
    }

    el.classList.remove('hidden');
    el.innerHTML = _p3Tabs.map((tab, i) => {
      const isActive = i === _p3ActiveTabIdx;
      const canClose = tab.id !== 'default';
      return `<div class="wb-p3-tab${isActive ? ' active' : ''}" data-p3-tab="${i}" title="${_esc(tab.title)}">
        <span class="wb-p3-tab-label">${_esc(tab.title)}</span>
        ${canClose ? `<button class="wb-p3-tab-close" data-p3-close="${i}">×</button>` : ''}
      </div>`;
    }).join('');

    el.querySelectorAll('[data-p3-tab]').forEach(t => {
      t.addEventListener('click', e => {
        if (e.target.closest('[data-p3-close]')) return;
        _switchP3Tab(+t.dataset.p3Tab);
      });
    });
    el.querySelectorAll('[data-p3-close]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        _closeP3Tab(+btn.dataset.p3Close);
      });
    });
  }

  function _switchP3Tab(idx) {
    if (idx < 0 || idx >= _p3Tabs.length) return;
    _p3ActiveTabIdx = idx;
    _renderP3Tabs();
    _renderP3ActiveContent();
  }

  function _closeP3Tab(idx) {
    if (idx <= 0 || idx >= _p3Tabs.length) return; // 不能关闭 default
    _p3Tabs.splice(idx, 1);
    if (_p3ActiveTabIdx >= _p3Tabs.length) _p3ActiveTabIdx = _p3Tabs.length - 1;
    // 如果切回 default，清除 TLS 实例
    if (_p3Tabs[_p3ActiveTabIdx]?.id === 'default') { _p3Tls = null; _p3TlsKey = null; }
    _renderP3Tabs();
    _renderP3ActiveContent();
  }

  async function _renderP3ActiveContent() {
    const tab    = _p3Tabs[_p3ActiveTabIdx];
    const bodyEl = document.getElementById('wb-body-3');
    const tlsEl  = document.getElementById('wb-p3-tls');
    if (!tab || !bodyEl || !tlsEl) return;

    if (tab.id === 'default') {
      // 显示我的主业务
      if (_p3Tls) { _p3Tls = null; _p3TlsKey = null; }
      bodyEl.style.display = '';
      tlsEl.style.display  = 'none';
      _renderPanelContext(_panelData[3] || []);
      return;
    }

    // 显示清单 TLS（或 iframe）
    bodyEl.style.display = 'none';
    tlsEl.style.display  = '';

    const fn = _cf();
    if (!fn) { tlsEl.innerHTML = '<div class="wb-empty">请先登录</div>'; return; }

    const itemType = tab.itemType || 'task';
    const listGid  = tab.listGid;
    const tlsKey   = itemType + ':' + listGid;

    // ── BOP 版本：用工艺流程图布局模式（lineage view）渲染 ──
    if (itemType === 'bop_version') {
      const existingIframe = tlsEl.querySelector('iframe[data-version-gid]');
      if (!existingIframe || existingIframe.dataset.versionGid !== listGid) {
        _p3Tls    = null;
        _p3TlsKey = tlsKey;
        // 网页版：craft-plugin 在 /packages/ 下；Electron 版：相对路径
        const _isWeb = window.parent?.electronAPI?._isElectron === false;
        const src = _isWeb
          ? `/packages/craft-plugin/web/lineage_view/index.html?bop_version_gid=${encodeURIComponent(listGid)}&_t=${Date.now()}`
          : `../lineage_view/index.html?bop_version_gid=${encodeURIComponent(listGid)}`;
        tlsEl.innerHTML = `<iframe src="${src}" data-version-gid="${listGid}" style="width:100%;height:100%;border:none;display:block;" allowfullscreen></iframe>`;
        // 主题同步
        const iframe = tlsEl.querySelector('iframe');
        iframe.addEventListener('load', () => {
          const theme = document.documentElement.dataset.theme || document.body.dataset.theme || 'light';
          try { iframe.contentWindow.postMessage({ type: 'theme', theme }, '*'); } catch (_) {}
        });
      }
      return;
    }

    // ── 飞书文档：在查看器面板里内联渲染（<webview> via Electron）──
    if (itemType === 'feishu_doc') {
      const url = tab.url || '';
      const existing = tlsEl.querySelector('[data-fsh-doc-url]');
      if (!existing || existing.dataset.fshDocUrl !== url) {
        _p3Tls = null; _p3TlsKey = tlsKey;
        // Electron 中 <webview> 绕过 X-Frame-Options；普通浏览器降级为 <iframe>
        const isElectron = !!window.electronAPI;
        if (isElectron) {
          tlsEl.innerHTML = `<webview src="${_esc(url)}" data-fsh-doc-url="${_esc(url)}"
            style="width:100%;height:100%;display:block;"
            allowpopups></webview>`;
        } else {
          tlsEl.innerHTML = `<iframe src="${_esc(url)}" data-fsh-doc-url="${_esc(url)}"
            style="width:100%;height:100%;border:none;display:block;"
            allow="fullscreen"></iframe>`;
        }
      }
      return;
    }

    // ── 知识文档：直接内联渲染，不打开整个知识库 Hub ──
    if (itemType === 'knowledge_doc') {
      if (tlsEl.dataset.renderedDocGid === listGid) return;
      tlsEl.innerHTML = '<div class="wb-loading" style="padding:12px">加载中…</div>';
      try {
        const item = await fn(`/api/knowledge_hub/items/${listGid}`);
        _renderKnowledgeDocPanel(tlsEl, item);
        tlsEl.dataset.renderedDocGid = listGid;
      } catch (e) {
        console.error('知识文档加载失败', e);
        tlsEl.innerHTML = '<div class="wb-empty">加载失败，请刷新</div>';
      }
      return;
    }

    // ── 项目：打开项目管理页并定位到该项目 ──
    if (itemType === 'project') {
      const existingIframe = tlsEl.querySelector('iframe[data-project-gid]');
      if (!existingIframe || existingIframe.dataset.projectGid !== listGid) {
        _p3Tls    = null;
        _p3TlsKey = tlsKey;
        const _isWeb2 = window.parent?.electronAPI?._isElectron === false;
        const src = _isWeb2
          ? `/packages/craft-plugin/web/project/project.html?project_gid=${encodeURIComponent(listGid)}`
          : `../project/project.html?project_gid=${encodeURIComponent(listGid)}`;
        tlsEl.innerHTML = `<iframe src="${src}" data-project-gid="${listGid}" style="width:100%;height:100%;border:none;display:block;" allowfullscreen></iframe>`;
        const iframe = tlsEl.querySelector('iframe');
        iframe.addEventListener('load', () => {
          const theme = document.documentElement.dataset.theme || document.body.dataset.theme || 'light';
          try { iframe.contentWindow.postMessage({ type: 'theme', theme }, '*'); } catch (_) {}
        });
      }
      return;
    }

    const cols  = WB_P1_COLS_MAP[itemType] || WB_P1_COLS_TASK;
    const apiFn = WB_P1_API_MAP[itemType];
    const url   = apiFn ? apiFn(listGid) : `/api/tasks?list_gid=${listGid}&limit=200`;

    let tlsData = [];
    try {
      tlsEl.innerHTML = '<div class="wb-loading" style="padding:12px">加载中…</div>';
      const res = await fn(url);
      tlsData = Array.isArray(res) ? res : (res.items || res.data || []);
      tlsData.forEach(row => { if (!row.item_type) row.item_type = itemType; });
    } catch (e) {
      console.error('面板3清单加载失败', e);
      tlsEl.innerHTML = '<div class="wb-empty">加载失败，请刷新</div>';
      return;
    }

    // tab 切换时重建 TLS
    if (_p3TlsKey !== tlsKey) {
      tlsEl.innerHTML = '';
      _p3Tls    = null;
      _p3TlsKey = tlsKey;
    }

    const _tlsDataRef = tlsData;
    if (!_p3Tls) {
      _p3Tls = new TreeListShell({
        mountEl:          tlsEl,
        forcedItemType:   itemType,
        listGid:          listGid || 'p3_fixed',
        showListSelector: false,
        compactToolbar:   true,
        columns:          cols.filter(c => c.defaultOn !== false),
        allColumns:       cols,
        parentField:      WB_P1_PARENT_MAP[itemType] || null,
        groupField:       WB_P1_GROUP_MAP[itemType]  || null,
        moduleId:         'wb_p3_' + itemType,
        onLoadLists:      () => [],
        onLoadData:       () => _tlsDataRef,
        onRowClick:       (row) => { _renderPanelDetail(row); _loadItemLinks(row); },
        detailMode:       'editable',
        autoFitColumns:   true,
        allowNewEntry:    true,
        onCreateEntry:    async (data) => {
          const { list_gid, ...fields } = data;
          return _submitNewItemByDomain(itemType, list_gid, fields);
        },
      });
      await _p3Tls.init();
    } else {
      await _p3Tls.refresh();
    }
  }

  // 新建清单（有权限才触发）
  async function _createList(sectionKey) {
    const title = await _promptText('新建文件', '');
    if (!title) return;
    const fn = _cf(); if (!fn) return;
    const shareScope = sectionKey === 'public' ? 'org' : 'private';
    try {
      await fn('/api/lists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, name: title, item_type: 'task', share_scope: shareScope }),
      });
      _panel1ListsCache = null;
      _renderP2Tree();
    } catch (e) { console.error('新建文件失败', e); }
  }



  let _centerTab = 3;

  // 链接列表和当前索引
  let _links       = [];
  let _linkIdx     = 0;

  // 日历状态
  let _calYear  = new Date().getFullYear();
  let _calMonth = new Date().getMonth();
  let _calPlanItems  = [];   // 当前过滤出的计划条目（供飞书日程加载后合并排序用）
  let _calFeishuItems = null; // 缓存最近一次飞书日程（null=尚未加载）
  function _wbTodayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }
  let _calSelectedDay = _wbTodayStr(); // 当前选中日（默认今日）

  // 持久化可见性（panels 1/2/5/6/7 + center + cal）
  const _LS_VIS = 'wb:panel-vis-v3';
  let _vis = _loadVis();

  function _loadVis() {
    try {
      const v = JSON.parse(localStorage.getItem(_lsk(_LS_VIS)) || '{}');
      return {
        1:      v[1]      !== false,
        2:      v[2]      !== false,
        center: v.center  !== false,
        cal:    v.cal     !== false,
        app:    v.app     !== false,
        4:      v[4]      === true,
        5:      v[5]      === true,
        6:      v[6]      === true,
      };
    } catch {
      return { 1:true, 2:true, center:true, cal:true, app:false, 4:false, 5:false, 6:false };
    }
  }

  function _saveVis() {
    localStorage.setItem(_lsk(_LS_VIS), JSON.stringify(_vis));
  }

  // ── 列宽比例（左列 fr，总计 60fr）───────────────────────────────────────
  const _LS_COL = 'wb:col-ratio';
  const _COL_TOTAL = 60;   // left + mid 总 fr
  const _COL_MIN   = 8;    // 最小 fr（防止面板太窄）
  let _leftFr = (() => {
    try { const v = parseFloat(localStorage.getItem(_lsk(_LS_COL))); return (v >= _COL_MIN && v <= _COL_TOTAL - _COL_MIN) ? v : 22; }
    catch { return 22; }
  })();

  function _applyColRatio() {
    document.documentElement.style.setProperty('--wb-lr', _leftFr + 'fr');
    document.documentElement.style.setProperty('--wb-mr', (_COL_TOTAL - _leftFr) + 'fr');
    // 仅树可见时同步更新 px 宽度（fr 无法与 px 混合 calc，需 JS 介入）
    if (_vis && !_vis[1] && _vis[2]) _syncTreeOnlyWidth();
  }

  // 计算"仅树面板"时左列的 px 宽度 = 按当前 fr 比例算出左列全宽 - 今日面板宽 - 内层分割条宽
  function _syncTreeOnlyWidth() {
    const panels = document.getElementById('wbPanels');
    if (!panels) return;
    const todayW = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue('--wb-today-w')
    ) || 126;
    const panelsW  = panels.getBoundingClientRect().width;
    const calW     = panels.classList.contains('wb-cal-hidden') ? 0 : 200;
    const rightFr  = panels.classList.contains('wb-right-open') ? 22 : 0;
    const totalFr  = _COL_TOTAL + rightFr;
    const fixedW   = 6 /* padding lr */ + 3 /* outer splitter */+ calW;
    const frPx     = (panelsW - fixedW) / totalFr;
    const treeW    = Math.max(60, Math.round(frPx * _leftFr - todayW - 3 /* inner splitter */));
    panels.style.setProperty('--wb-left-col', treeW + 'px');
  }

  function _initSplitter() {
    const splitter = document.getElementById('wbSplitterLeft');
    const panels   = document.getElementById('wbPanels');
    if (!splitter || !panels) return;

    splitter.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      e.preventDefault();

      const startX    = e.clientX;
      const startLeft = _leftFr;
      const totalPx   = panels.getBoundingClientRect().width;

      splitter.classList.add('dragging');
      panels.classList.add('wb-dragging');

      function onMove(ev) {
        const dx = ev.clientX - startX;
        // dx / totalPx 映射到 fr 变化量（总 fr = _COL_TOTAL）
        const deltaFr = (dx / totalPx) * _COL_TOTAL;
        _leftFr = Math.max(_COL_MIN, Math.min(_COL_TOTAL - _COL_MIN, startLeft + deltaFr));
        _applyColRatio();
      }

      function onUp() {
        splitter.classList.remove('dragging');
        panels.classList.remove('wb-dragging');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        localStorage.setItem(_lsk(_LS_COL), _leftFr.toFixed(2));
      }

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    // 双击重置
    splitter.addEventListener('dblclick', () => {
      _leftFr = 22;
      _applyColRatio();
      localStorage.setItem(_lsk(_LS_COL), _leftFr.toFixed(2));
    });
  }

  function _initInnerSplitter() {
    const splitter = document.getElementById('wbSplitterInner');
    if (!splitter) return;

    splitter.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      e.preventDefault();

      const startX = e.clientX;
      const startW = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--wb-today-w')
      ) || 126;

      splitter.classList.add('dragging');

      function onMove(ev) {
        const newW = Math.max(60, Math.min(320, startW + ev.clientX - startX));
        document.documentElement.style.setProperty('--wb-today-w', newW + 'px');
      }

      function onUp() {
        splitter.classList.remove('dragging');
        const w = parseFloat(
          getComputedStyle(document.documentElement).getPropertyValue('--wb-today-w')
        );
        localStorage.setItem(_lsk('wb:today-w'), w.toFixed(0));
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      }

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    splitter.addEventListener('dblclick', () => {
      document.documentElement.style.setProperty('--wb-today-w', '126px');
      localStorage.setItem(_lsk('wb:today-w'), '126');
    });
  }

  // ── 工具 ────────────────────────────────────────────────────────────────
  function _cf() { return window._cloudFetch || window.parent?._cloudFetch || null; }

  function _applyTheme() {
    const t = localStorage.getItem('system.theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
  }

  function _esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── 布局更新 ─────────────────────────────────────────────────────────────
  function _updateLayout() {
    const panels = document.getElementById('wbPanels');

    // [1] 今日待办面板 on/off
    const p1el = document.getElementById('wb-panel-1');
    if (p1el) p1el.classList.toggle('wb-panel-off', !_vis[1]);

    // [2] 内容树面板 on/off
    const p2el = document.getElementById('wb-panel-2');
    if (p2el) p2el.classList.toggle('wb-panel-off', !_vis[2]);

    // 内层分割条：两个面板都可见时才显示
    const innerSplit = document.getElementById('wbSplitterInner');
    if (innerSplit) innerSplit.style.display = (_vis[1] && _vis[2]) ? '' : 'none';

    // [4][5][6] 右侧面板单独 on/off
    [4, 5, 6].forEach(p => {
      const el = document.getElementById(`wb-panel-${p}`);
      if (el) el.classList.toggle('wb-panel-off', !_vis[p]);
    });
    // [A][C] 日历列两个面板（共用同一列）
    const appEl = document.getElementById('wb-panel-app');
    const calEl = document.getElementById('wb-panel-cal');
    const calHidden = !_vis.cal && !_vis.app;   // 两者都关才收起日历列

    if (!calHidden) {
      // 至少一个可见：各自独立 on/off，使 A/C 在列内互相撑满
      if (appEl) appEl.classList.toggle('wb-panel-off', !_vis.app);
      if (calEl) calEl.classList.toggle('wb-panel-off', !_vis.cal);
    }
    // calHidden=true 时：整列由 wb-cal-hidden 隐藏，不改变面板 flex 状态，
    // 避免触发任何额外的上下展开/收缩动作

    // grid-template-columns：用 class 驱动，不对列元素用 display:none
    const rightOpen  = _vis[4] || _vis[5] || _vis[6];
    const leftHidden = !_vis[1] && !_vis[2];  // 两个面板都关时才收起左列
    const wasCalHidden = panels.classList.contains('wb-cal-hidden');

    // 日历列关闭时：立即 collapse（不 transition），避免宽度过渡中内容 reflow 导致视觉跳动
    // 日历列打开时：正常 transition（0px→200px 平滑展开）
    if (!wasCalHidden && calHidden) {
      panels.style.transition = 'none';
      panels.classList.add('wb-cal-hidden');
      panels.getBoundingClientRect(); // 强制同步 layout，提交瞬间 collapse
      panels.style.transition = '';
    } else {
      panels.classList.toggle('wb-cal-hidden', calHidden);
    }

    panels.classList.toggle('wb-right-open',  rightOpen);
    panels.classList.toggle('wb-mid-hidden',  !_vis.center);
    panels.classList.toggle('wb-left-hidden', leftHidden);
    // 个别左列面板关闭时的 grid 调整
    panels.classList.toggle('wb-p1-hidden', !_vis[1] && _vis[2]);
    panels.classList.toggle('wb-p2-hidden',  _vis[1] && !_vis[2]);
    // 非"仅树可见"模式时清除 px 覆盖，恢复 fr 比例
    if (_vis[1] || !_vis[2]) panels.style.removeProperty('--wb-left-col');
    // 应用列宽比例 CSS 变量
    _applyColRatio();
  }

  // ── 面板切换 ─────────────────────────────────────────────────────────────
  function _togglePanel(n) {
    if (n === 3) {
      // 中列切换
      if (!_vis.center) {
        _vis.center = true;
        _switchCenterTab(_centerTab);
        _focusPanel(3);
      } else if (_focusedPanel === 3) {
        _vis.center = false;  // 已聚焦 → 隐藏
        _blurPanel();
      } else {
        _focusPanel(3);       // 可见但未聚焦 → 聚焦
      }
    } else if (n === 1) {
      if (!_vis[n]) {
        _vis[n] = true;
        _focusPanel(n);
      } else if (_focusedPanel === n) {
        _vis[n] = false;
        _blurPanel();
      } else {
        _focusPanel(n);
      }
    } else if (n === 2) {
      if (!_vis[2]) {
        _vis[2] = true;
        _focusPanel(2);
        _renderPanel(2);
      } else if (_focusedPanel === 2) {
        _vis[2] = false;
        _blurPanel();
      } else {
        _focusPanel(2);
      }
    } else if (n === 4 || n === 5 || n === 6) {
      _vis[n] = !_vis[n];
      if (_vis[n]) {
        if (_panelData[n] !== undefined) _renderPanel(n);
        else _loadRightPanel(n);
      }
    } else if (n === 'A') {
      _vis.app = !_vis.app;
      if (_vis.app) _renderAppPanel();
    }
    _saveVis();
    _updateLayout();
    _updateStatusbar();
  }

  function _toggleCal() {
    _vis.cal = !_vis.cal;
    _saveVis();
    _updateLayout();
    _updateStatusbar();
    if (_vis.cal) _renderCalendar();
  }

  function _toggleMidMax() {
    _midMaximized = !_midMaximized;
    document.getElementById('wbPanels')?.classList.toggle('wb-mid-max', _midMaximized);
  }

  // ── 中列 tab 切换（pane-4 已移除，始终显示 pane-3）──────────────────────
  function _switchCenterTab(tab) {
    _centerTab = tab === 4 ? 3 : (tab || 3); // 兼容旧调用，4 强制转 3
    const pane3 = document.getElementById('wb-pane-3');
    const pane4 = document.getElementById('wb-pane-4');
    if (pane3) pane3.classList.remove('hidden');
    if (pane4) pane4.classList.add('hidden');    // 关联面板永久隐藏
    _renderP3Tabs();
  }

  // ── 面板聚焦 ──────────────────────────────────────────────────────────────
  function _focusPanel(n) {
    document.querySelectorAll('.wb-panel').forEach(p =>
      p.classList.remove('wb-panel-focused')
    );
    document.getElementById(`wb-panel-${n}`)?.classList.add('wb-panel-focused');
    _focusedPanel = n;
    _updateStatusbar();
  }

  function _blurPanel() {
    document.querySelectorAll('.wb-panel').forEach(p =>
      p.classList.remove('wb-panel-focused')
    );
    _focusedPanel = null;
    _updateStatusbar();
  }

  // ── 状态栏 ───────────────────────────────────────────────────────────────
  const _PANEL_ACTIONS = {
    1: [{key:'n',label:'新建'},{key:'f',label:'筛选'},{key:'↑↓',label:'移动'},{key:'Enter',label:'打开详情'}],
    2: [{key:'f',label:'筛选'}],
    3: [{key:'f',label:'筛选'},{key:'↑↓',label:'移动'},{key:'Enter',label:'进入'}],
    4: [{key:'↑↓',label:'移动'},{key:'Enter',label:'打开'}],
    5: [],
    6: [],
  };

  function _updateStatusbar() {
    // 面板按钮 1-6
    document.querySelectorAll('.wb-sb-panel-btn').forEach(btn => {
      const p = +btn.dataset.panel;
      let visible = false;
      if (p === 3)      visible = _vis.center;
      else if (p === 1) visible = _vis[1];
      else              visible = _vis[p];
      btn.classList.toggle('wb-sb-visible',  visible);
      btn.classList.toggle('wb-sb-hidden-p', !visible);
    });

    // 日历按钮
    const calBtn = document.getElementById('wbCalBtn');
    if (calBtn) {
      calBtn.classList.toggle('wb-sb-visible',  _vis.cal);
      calBtn.classList.toggle('wb-sb-hidden-p', !_vis.cal);
    }

    // App 按钮
    const appBtn = document.getElementById('wbAppBtn');
    if (appBtn) {
      appBtn.classList.toggle('wb-sb-visible',  _vis.app);
      appBtn.classList.toggle('wb-sb-hidden-p', !_vis.app);
    }

    // 右侧通知徽标
    [4, 5, 6].forEach(p => {
      const badge = document.getElementById(`wb-badge-${p}`);
      if (!badge) return;
      const count = (_panelData[p] || []).length;
      badge.textContent = count > 0 ? String(count) : '';
      badge.style.display = (count > 0 && !_vis[p]) ? 'inline-block' : 'none';
    });

    // 上下文操作
    const actions = _focusedPanel ? (_PANEL_ACTIONS[_focusedPanel] || []) : [];
    const el = document.getElementById('wbSbActions');
    el.innerHTML = actions.map(a =>
      `<button class="wb-sb-action" data-key="${_esc(a.key)}">${_esc(a.key)} ${_esc(a.label)}</button>`
    ).join('');
    el.querySelectorAll('[data-key]').forEach(btn =>
      btn.addEventListener('click', () => _handleKey(btn.dataset.key))
    );
  }

  // ── 键盘 ─────────────────────────────────────────────────────────────────
  function _handleKey(key) {
    const handlers = {
      'f':         () => _focusedPanel && _activateFilter(_focusedPanel),
      'n':         () => { if (_focusedPanel === 1) _openNewItemModal(); },
      'Enter':     () => _focusedPanel && _openSelected(_focusedPanel),
      'ArrowUp':   () => _focusedPanel && _navigateRows(_focusedPanel, -1),
      'ArrowDown': () => _focusedPanel && _navigateRows(_focusedPanel, +1),
      'Tab':       () => _focusedPanel === 4 && _cycleLinkTab(+1),
    };
    handlers[key]?.call();
  }

  document.addEventListener('keydown', e => {
    if (e.target.matches('input,textarea,select')) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    // 数字键 1-6
    if ('123456'.includes(e.key) && e.key.length === 1) {
      // 3 双击：最大化 / 还原中列
      if (e.key === '3') {
        const now = Date.now();
        if (now - _midMaxLastTap < 350) {
          _midMaxLastTap = 0;
          _toggleMidMax();
          e.preventDefault();
          return;
        }
        _midMaxLastTap = now;
      }
      _togglePanel(+e.key);
      e.preventDefault();
      return;
    }

    // c → 日历
    if (e.key === 'c' || e.key === 'C') {
      if (!e.target.matches('input,textarea')) {
        _toggleCal();
        e.preventDefault();
      }
      return;
    }

    // a → App 面板
    if (e.key === 'a' || e.key === 'A') {
      if (!e.target.matches('input,textarea')) {
        _togglePanel('A');
        e.preventDefault();
      }
      return;
    }

    // r → 小柔对话面板
    if (e.key === 'r' || e.key === 'R') {
      const chat = document.getElementById('wbFloatChat');
      const inp  = document.getElementById('wbFcInp');
      if (!chat) return;
      const open = chat.style.display !== 'none';
      chat.style.display = open ? 'none' : 'flex';
      if (!open) { _updateAiCtx(); inp?.focus(); }
      document.getElementById('wbAiBallToggleBtn')?.classList.toggle('wb-sb-visible', !open);
      e.preventDefault();
      return;
    }

    // Escape
    if (e.key === 'Escape') {
      // 先关闭小柔面板（若已打开且输入框无焦点）
      const chat = document.getElementById('wbFloatChat');
      if (chat && chat.style.display !== 'none') {
        chat.style.display = 'none';
        document.getElementById('wbAiBallToggleBtn')?.classList.remove('wb-sb-visible');
        e.preventDefault();
        return;
      }
      // 先关闭面板3详情条
      if (_p3DetailOpen) {
        _toggleDetailStrip('p3');
        e.preventDefault();
        return;
      }
      if (_focusedPanel) {
        const filterEl = document.getElementById(`wb-filter-${_focusedPanel}`);
        if (filterEl && !filterEl.classList.contains('hidden')) {
          _deactivateFilter(_focusedPanel);
          e.preventDefault();
          return;
        }
        _blurPanel();
        e.preventDefault();
      }
      return;
    }

    if (!_focusedPanel) return;

    if (e.key === 'Tab' && _focusedPanel === 3 && _centerTab === 4) {
      _cycleLinkTab(e.shiftKey ? -1 : +1);
      e.preventDefault();
      return;
    }

    if (['ArrowUp','ArrowDown','Enter','f','n'].includes(e.key)) {
      _handleKey(e.key);
      e.preventDefault();
    }
  });

  // ── 筛选 ─────────────────────────────────────────────────────────────────
  function _activateFilter(panel) {
    const wrap = document.getElementById(`wb-filter-${panel}`);
    if (!wrap) return;
    wrap.classList.remove('hidden');
    document.getElementById(`wb-filter-input-${panel}`)?.focus();
  }

  function _deactivateFilter(panel) {
    const wrap = document.getElementById(`wb-filter-${panel}`);
    if (!wrap) return;
    wrap.classList.add('hidden');
    const input = document.getElementById(`wb-filter-input-${panel}`);
    if (input) input.value = '';
    _filterText[panel] = '';
    _renderPanel(panel);
  }

  function _bindFilterInputs() {
    [1, 3].forEach(p => {
      const input = document.getElementById(`wb-filter-input-${p}`);
      if (!input) return;
      input.addEventListener('input', () => {
        _filterText[p] = input.value.trim().toLowerCase();
        _renderPanel(p);
      });
      input.addEventListener('keydown', e => {
        if (e.key === 'Escape')     { e.stopPropagation(); _deactivateFilter(p); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); _navigateRows(p, +1); }
        else if (e.key === 'ArrowUp')   { e.preventDefault(); _navigateRows(p, -1); }
        else if (e.key === 'Enter')     { e.preventDefault(); _openSelected(p); }
      });
    });
  }

  // ── 行导航 ───────────────────────────────────────────────────────────────
  function _navigateRows(panel, delta) {
    const bodyId = `wb-body-${panel}`;
    const body = document.getElementById(bodyId);
    if (!body) return;
    const rows = Array.from(body.querySelectorAll('.wb-row, .wb-link-tab'));
    if (!rows.length) return;
    const cur = _selectedIdx[panel] ?? -1;
    const next = Math.max(0, Math.min(rows.length - 1, cur + delta));
    _selectRow(panel, next, rows);
  }

  function _selectRow(panel, idx, rows) {
    if (!rows) {
      const body = document.getElementById(`wb-body-${panel}`);
      rows = body ? Array.from(body.querySelectorAll('.wb-row')) : [];
    }
    rows.forEach((r, i) => r.classList.toggle('selected', i === idx));
    _selectedIdx[panel] = idx;
    rows[idx]?.scrollIntoView({ block: 'nearest' });
  }

  function _openSelected(panel) {
    const body = document.getElementById(`wb-body-${panel}`);
    if (!body) return;
    const rows = Array.from(body.querySelectorAll('.wb-row'));
    const idx = _selectedIdx[panel] ?? -1;
    if (idx >= 0 && idx < rows.length) rows[idx].click();
  }

  // ── 渲染面板 ─────────────────────────────────────────────────────────────
  function _renderPanel(panel) {
    _selectedIdx[panel] = -1;
    const data = _panelData[panel] || [];
    switch (panel) {
      case 1:
        _renderPanelToday(_panelData[1] || []);
        if (_vis.cal) _renderCalendar();
        break;
      case 2:
        _renderP2Tree();
        break;
      case 3:
        _renderP3Tabs();
        _renderP3ActiveContent();
        break;
      case 4: _renderPanelFollows(data); break;
      case 5: _renderPanelAlerts(data);  break;
      case 6: _renderPanelStatus(data);  break;
    }
  }

  // ── 面板1 标题栏内 Tabs ──────────────────────────────────────────────────
  function _renderP1TabsInline() {
    const bar = document.getElementById('wb-p1-tabs-inline');
    if (!bar) return;
    bar.innerHTML = _p1Tabs.map((tab, i) => {
      const label    = tab.type === 'today' ? '今日清单' : (tab.listTitle || '清单');
      const isActive = i === _p1ActiveTab;
      const canClose = tab.type !== 'today';
      return `<div class="wb-p1-ti-tab${isActive ? ' active' : ''}" data-p1-tab="${i}" title="${_esc(label)}">
        <span class="wb-p1-ti-label">${_esc(label)}</span>
        ${canClose ? `<button class="wb-p1-ti-close" data-p1-close="${i}">×</button>` : ''}
      </div>`;
    }).join('');
    bar.querySelectorAll('[data-p1-tab]').forEach(el => {
      el.addEventListener('click', e => {
        if (e.target.closest('[data-p1-close]')) return;
        _switchP1Tab(+el.dataset.p1Tab);
      });
    });
    bar.querySelectorAll('[data-p1-close]').forEach(btn => {
      btn.addEventListener('click', e => { e.stopPropagation(); _closeP1Tab(+btn.dataset.p1Close); });
    });
  }

  function _switchP1Tab(idx) {
    if (idx < 0 || idx >= _p1Tabs.length) return;
    _p1ActiveTab = idx;
    _filterText[1] = '';
    const fw = document.getElementById('wb-filter-1');
    const fi = document.getElementById('wb-filter-input-1');
    if (fw) fw.classList.add('hidden');
    if (fi) fi.value = '';
    _renderPanel(1);
  }

  function _closeP1Tab(idx) {
    if (!_p1Tabs[idx] || _p1Tabs[idx].type === 'today') return;
    _p1Tabs.splice(idx, 1);
    if (_p1ActiveTab >= _p1Tabs.length) _p1ActiveTab = _p1Tabs.length - 1;
    _saveP1Tabs();
    _filterText[1] = '';
    _renderPanel(1);
  }

  function _addP1Tab(opt) {
    if (opt.type === 'today') {
      const idx = _p1Tabs.findIndex(t => t.type === 'today');
      if (idx >= 0) { _p1ActiveTab = idx; _renderPanel(1); }
      return;
    }
    const existIdx = _p1Tabs.findIndex(t => t.type === 'list' && t.listGid === opt.listGid);
    if (existIdx >= 0) {
      _switchP1Tab(existIdx);
    } else {
      _p1Tabs.push({ type: 'list', listGid: opt.listGid, listTitle: opt.listTitle, itemType: opt.itemType });
      _p1ActiveTab = _p1Tabs.length - 1;
      _saveP1Tabs();
      _filterText[1] = '';
      _renderPanel(1);
    }
  }

  // [1] 今日清单（多来源、分组、可排序）
  function _renderPanelToday(items) {
    const body = document.getElementById('wb-p1-today') || document.getElementById('wb-body-1');
    if (!body) return;

    const filter = (_filterText[1] || '').toLowerCase();
    const _SF_MAP = {
      pending:  ['pending', 'open', '', null, undefined],
      progress: ['in_progress'],
      done:     ['done', 'completed', 'resolved'],
      closed:   ['cancelled', 'closed'],
    };
    const sfKeys = _p1Settings.statusFilter || ['pending','progress','done','closed'];
    const sfAll  = sfKeys.length === 0 || sfKeys.length >= 4;
    const sfSet  = sfAll ? null : new Set(sfKeys.flatMap(k => _SF_MAP[k] || []));
    const filtered = items
      .filter(it => !filter || (it.title || '').toLowerCase().includes(filter))
      .filter(it => sfAll || sfSet.has(it.status ?? ''));

    if (!filtered.length) {
      body.innerHTML = '<div class="wb-empty">暂无待办事项</div>';
      _setCount(1, 0, 0);
      return;
    }

    // ── 排序 ──
    const sortKey = _p1Settings.sortBy || 'scheduled_date';
    const SORT_PRIO = { urgent:0, high:1, medium:2, normal:3, low:4 };
    const sorted = [...filtered].sort((a, b) => {
      switch (sortKey) {
        case 'scheduled_date': {
          const da = a.scheduled_date ? String(a.scheduled_date).substring(0, 10) : '9999-12-31';
          const db = b.scheduled_date ? String(b.scheduled_date).substring(0, 10) : '9999-12-31';
          return da < db ? -1 : da > db ? 1 : 0;
        }
        case 'priority': {
          const pa = SORT_PRIO[a.priority] ?? 99;
          const pb = SORT_PRIO[b.priority] ?? 99;
          return pa - pb;
        }
        case 'status':  return (a.status || '').localeCompare(b.status || '');
        case 'title':   return (a.title  || '').localeCompare(b.title  || '');
        default: return 0;
      }
    });

    // ── 分组 ──
    const groupBy  = _p1Settings.groupBy || 'date';
    const groups   = _groupP1Items(sorted, groupBy);
    const ORDER    = _groupOrder(groupBy);
    const keys     = Object.keys(groups).sort((a, b) => {
      const ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
      if (ia >= 0 && ib >= 0) return ia - ib;
      if (ia >= 0) return -1; if (ib >= 0) return 1;
      return a.localeCompare(b);
    });

    const _n = new Date();
    const todayStr = `${_n.getFullYear()}-${String(_n.getMonth()+1).padStart(2,'0')}-${String(_n.getDate()).padStart(2,'0')}`;

    // ── 行渲染 helper ──
    const domainLabel  = { task:'T', issue:'I', bop:'B', knowledge:'K', rule:'R' };
    const statusDotCls = (s) => ['done','completed','resolved'].includes(s) ? 'sdot-done'
                               : s === 'in_progress' ? 'sdot-progress'
                               : ['cancelled','closed'].includes(s) ? 'sdot-closed' : 'sdot-pending';

    const rowHtml = (item, flatIdx) => {
      const type  = item.item_type || 'task';
      const d     = item.scheduled_date ? String(item.scheduled_date).substring(0, 10) : '';
      const over  = !!d && d < todayStr;
      const dl    = !d ? '' : over ? '逾期' : d === todayStr ? '今日' : d.slice(5);
      return `<div class="wb-row" data-idx="${flatIdx}" data-gid="${item.gid}" data-type="${type}"
        data-item='${JSON.stringify(item).replace(/'/g,"&#39;")}'>
        <span class="wb-row-domain-tag type-${type}">${domainLabel[type] || type}</span>
        <span class="wb-row-status-dot ${statusDotCls(item.status)}"></span>
        <span class="wb-row-title" title="${_esc(item.title)}">${_esc(item.title)}</span>
        ${dl ? `<span class="wb-row-meta" style="${over?'color:var(--color-danger)':''}">${dl}</span>` : ''}
      </div>`;
    };

    // ── 构建 HTML ──
    let html = '';
    keys.forEach(key => {
      const grpItems = groups[key];
      const isOpen = _p1GroupOpen[key] !== false;
      const lblCls = key === '今日' ? 'today' : '';
      html += `<div class="wb-p1-group ${isOpen ? 'is-open' : ''}" data-grp="${_esc(key)}">
        <div class="wb-p1-grp-hdr">
          <svg class="wb-p1-grp-chev" width="8" height="8" viewBox="0 0 10 10" fill="none"
            stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3,2 7,5 3,8"/>
          </svg>
          <span class="wb-p1-grp-label ${lblCls}">${_esc(key)}</span>
          <span class="wb-p1-grp-count">${grpItems.length}</span>
        </div>
        <div class="wb-p1-grp-body">`;
      grpItems.forEach(item => { html += rowHtml(item, sorted.indexOf(item)); });
      html += `</div></div>`;
    });
    body.innerHTML = html;

    // ── 分组折叠/展开 ──
    body.querySelectorAll('.wb-p1-grp-hdr').forEach(hdr => {
      hdr.addEventListener('click', () => {
        const grp = hdr.closest('.wb-p1-group');
        grp.classList.toggle('is-open');
        _p1GroupOpen[grp.dataset.grp] = grp.classList.contains('is-open');
      });
    });

    // ── 行点击 / 右键 ──
    body.querySelectorAll('.wb-row').forEach(row => {
      row.addEventListener('click', () => {
        _selectRow(1, parseInt(row.dataset.idx));
      });
      row.addEventListener('contextmenu', e => {
        e.preventDefault();
        _selectRow(1, parseInt(row.dataset.idx));
        try {
          const item = JSON.parse(row.dataset.item);
          _showP1RowCtxMenu(e, item);
        } catch (_) {}
      });
    });
    _setCount(1, filtered.length, items.length);
  }

  // 按 groupBy 对 items 分组，返回 { groupKey: [items] }
  function _groupP1Items(items, groupBy) {
    const _n = new Date();
    const todayStr = `${_n.getFullYear()}-${String(_n.getMonth()+1).padStart(2,'0')}-${String(_n.getDate()).padStart(2,'0')}`;
    // week boundaries using local date arithmetic (avoids UTC midnight offset)
    const dow      = _n.getDay(); // 0=Sun,1=Mon,...
    const diffMon  = dow === 0 ? -6 : 1 - dow;
    const monday   = new Date(_n.getFullYear(), _n.getMonth(), _n.getDate() + diffMon);
    const sunday   = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6);
    const nextSun  = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 13);
    const pad = (n) => String(n).padStart(2,'0');
    const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
    const sundayStr  = fmt(sunday);
    const nextSunStr = fmt(nextSun);
    const groups = {};
    const add = (k, it) => { if (!groups[k]) groups[k] = []; groups[k].push(it); };
    for (const item of items) {
      switch (groupBy) {
        case 'date': {
          const d = item.scheduled_date ? String(item.scheduled_date).substring(0, 10) : null;
          if (!d)                    add('未安排', item);
          else if (d <= todayStr)    add('今日',   item); // includes overdue (d < today)
          else if (d <= sundayStr)   add('本周',   item);
          else if (d <= nextSunStr)  add('下周',   item);
          else                       add('将来',   item);
          break;
        }
        case 'domain': {
          const m = { task:'任务', issue:'问题', bop:'BOP', knowledge:'知识', rule:'规则' };
          add(m[item.item_type] || item.item_type, item);
          break;
        }
        case 'priority': {
          const m = { urgent:'紧急', high:'高', medium:'中', normal:'正常', low:'低' };
          add(m[item.priority] || (item.priority ? item.priority : '无优先级'), item);
          break;
        }
        case 'status': {
          const m = { pending:'待办', in_progress:'进行中', done:'已完成',
                      completed:'已完成', open:'待处理', resolved:'已解决',
                      active:'活动', draft:'草稿', archived:'已归档' };
          add(m[item.status] || item.status || '未知', item);
          break;
        }
        default: add('全部', item);
      }
    }
    return groups;
  }

  // 分组显示顺序
  function _groupOrder(groupBy) {
    switch (groupBy) {
      case 'date':     return ['今日','本周','下周','将来','未安排'];
      case 'domain':   return ['任务','问题','BOP','知识','规则'];
      case 'priority': return ['紧急','高','中','正常','低','无优先级'];
      case 'status':   return ['待办','进行中','待处理','活动','草稿','已完成','已解决','已归档','未知'];
      default: return [];
    }
  }

  // ── 面板1 设置浮层 ─────────────────────────────────────────────────────────
  // ── 面板1 条目来源：领域 + 清单过滤 ──────────────────────────────────────
  const _P1_DOMAINS = [
    { value: 'task',      label: '任务',   itemType: 'task' },
    { value: 'issue',     label: '问题',   itemType: 'issue' },
    { value: 'bop',       label: 'BOP全域', hasBopSub: true },
    { value: 'feishu',    label: '飞书日历', calOnly: true },
    { value: 'knowledge', label: '知识域', itemType: 'knowledge' },
    { value: 'rule',      label: '规则域', itemType: 'rule' },
  ];
  const _NI_DOMAIN_FIELDS = {
    task: [
      { key:'title',         label:'标题',   type:'text',   required:true },
      { key:'priority',      label:'优先级', type:'select',
        options:[['low','低'],['normal','普通'],['medium','中'],['high','高'],['urgent','紧急']], def:'medium' },
      { key:'time_estimate', label:'时长',   type:'num_presets', presets:[15,30,60], def:30 },
      { key:'due_date',      label:'截止日', type:'date' },
    ],
    issue: [
      { key:'title',    label:'标题',   type:'text',   required:true },
      { key:'severity', label:'严重度', type:'select',
        options:[['low','低'],['medium','中'],['high','高'],['critical','严重']], def:'medium' },
    ],
    knowledge: [
      { key:'title',      label:'标题', type:'text', required:true },
      { key:'entry_type', label:'类型', type:'select',
        options:[['guide','指南'],['standard','标准'],['checklist','检查表'],['template','模板']], def:'guide' },
    ],
    rule: [
      { key:'name',              label:'名称',   type:'text',   required:true },
      { key:'rule_type',         label:'规则类型', type:'select',
        options:[['process','工艺'],['quality','质量'],['safety','安全']], def:'process' },
      { key:'enforcement_level', label:'约束级', type:'select',
        options:[['advisory','建议'],['mandatory','强制']], def:'advisory' },
    ],
  };
  const _p1DomainListsCache = {}; // domain → list[]（懒加载后缓存）

  function _renderP1SrcSection(srcBody) {
    if (!srcBody) return;
    srcBody.innerHTML = _P1_DOMAINS.map(d => {
      const isChecked = _p1Settings.sources.includes(d.value);
      const lf = (_p1Settings.listFilter || {})[d.value];
      const filterCount = (Array.isArray(lf) && lf.length > 0) ? lf.length : 0;
      const badge = filterCount > 0 ? `<span class="wb-p1-filter-badge">${filterCount}</span>` : '';
      const expandBtn = (d.itemType || d.hasBopSub) ? `
        <button class="wb-p1-expand-btn" data-expand="${d.value}" title="筛选具体清单">
          <svg width="7" height="7" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3,2 7,5 3,8"/></svg>
        </button>` : '';
      return `
        <div class="wb-p1-domain-row" data-domain="${d.value}">
          <label class="wb-p1-sp-item" style="flex:1;min-width:0">
            <input type="checkbox" class="wb-p1-src" value="${d.value}"${isChecked ? ' checked' : ''}>
            <span>${d.label}</span>${badge}
          </label>${expandBtn}
        </div>
        ${(d.itemType || d.hasBopSub) ? `<div class="wb-p1-list-sub" id="wb-p1-lsub-${d.value}" hidden></div>` : ''}`;
    }).join('');

    // 领域 checkbox
    srcBody.querySelectorAll('.wb-p1-src').forEach(cb => {
      cb.addEventListener('change', () => {
        const checked = [...srcBody.querySelectorAll('.wb-p1-src:checked')].map(el => el.value);
        if (!checked.length) { cb.checked = true; return; }
        const unchecked = _P1_DOMAINS.map(d => d.value).filter(v => !checked.includes(v));
        // 取消勾选的域：清除子项过滤、取消子项勾选、移除 badge
        unchecked.forEach(domain => {
          if (_p1Settings.listFilter) delete _p1Settings.listFilter[domain];
          const sub = document.getElementById(`wb-p1-lsub-${domain}`);
          sub?.querySelectorAll('input[type="checkbox"]').forEach(c => { c.checked = false; });
          srcBody.querySelector(`.wb-p1-domain-row[data-domain="${domain}"]`)
            ?.querySelector('.wb-p1-filter-badge')?.remove();
        });
        // 新勾选的域：清除过滤（等同全选），并勾选已渲染的子项
        const prev = new Set(_p1Settings.sources || []);
        checked.filter(v => !prev.has(v)).forEach(domain => {
          if (_p1Settings.listFilter) delete _p1Settings.listFilter[domain];
          const sub = document.getElementById(`wb-p1-lsub-${domain}`);
          sub?.querySelectorAll('input[type="checkbox"]').forEach(c => { c.checked = true; });
          srcBody.querySelector(`.wb-p1-domain-row[data-domain="${domain}"]`)
            ?.querySelector('.wb-p1-filter-badge')?.remove();
        });
        _p1Settings.sources = checked;
        _saveP1Settings();
        _scheduleP1Reload();
        // 飞书日历勾选状态变化时刷新 C 面板日程和状态栏
        if (_vis.cal) _loadFeishuAgenda(_calSelectedDay);
        window.parent?.TaskTimeline?.refresh?.();
      });
    });

    // 展开按钮
    srcBody.querySelectorAll('.wb-p1-expand-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const domain = btn.dataset.expand;
        const sub = document.getElementById(`wb-p1-lsub-${domain}`);
        if (!sub) return;
        const willExpand = sub.hidden;
        sub.hidden = !willExpand;
        btn.classList.toggle('expanded', willExpand);
        if (willExpand) _loadDomainListsSub(domain, sub);
      });
    });
  }

  async function _loadDomainListsSub(domain, subEl) {
    if (domain === 'bop') {
      if (_p1DomainListsCache[domain]) {
        _renderBopVersionSub(_p1DomainListsCache[domain], subEl);
        return;
      }
      subEl.innerHTML = '<span class="wb-p1-sp-loading">加载中…</span>';
      const fn = _cf(); if (!fn) return;
      try {
        const [bopRes, pbomRes] = await Promise.allSettled([
          fn('/api/bop/versions'),
          fn('/api/ebom/snapshots'),
        ]);
        const bopVers = (bopRes.status === 'fulfilled'
          ? (bopRes.value?.versions || bopRes.value?.data || bopRes.value || [])
          : []).map(r => ({
            gid: 'bv:' + r.gid,
            name: (r.bop_name || r.version_name || r.gid) + (r.version_tag ? ` (${r.version_tag})` : ''),
            _group: 'BOP版本',
          }));
        const pbomVers = (pbomRes.status === 'fulfilled'
          ? (pbomRes.value?.data || pbomRes.value || [])
          : []).map(r => ({
            gid: 'pv:' + r.gid,
            name: r.name || r.version_tag || r.gid,
            _group: 'PBOM版本',
          }));
        const combined = [...bopVers, ...pbomVers];
        _p1DomainListsCache[domain] = combined;
        _renderBopVersionSub(combined, subEl);
      } catch {
        subEl.innerHTML = '<span class="wb-p1-sp-loading" style="color:var(--color-red,#f38ba8)">加载失败</span>';
      }
      return;
    }

    if (_p1DomainListsCache[domain]) {
      _renderP1ListCheckboxes(domain, _p1DomainListsCache[domain], subEl);
      return;
    }
    subEl.innerHTML = '<span class="wb-p1-sp-loading">加载中…</span>';
    const fn = _cf();
    if (!fn) return;
    try {
      const res = await fn(`/api/lists?item_type=${domain}`);
      const lists = Array.isArray(res) ? res : (res.data || res.lists || []);
      _p1DomainListsCache[domain] = lists;
      _renderP1ListCheckboxes(domain, lists, subEl);
    } catch {
      subEl.innerHTML = '<span class="wb-p1-sp-loading" style="color:var(--color-red,#f38ba8)">加载失败</span>';
    }
  }

  function _renderBopVersionSub(items, subEl) {
    if (!items.length) {
      subEl.innerHTML = '<span class="wb-p1-sp-loading">暂无版本</span>';
      return;
    }
    const lf = (_p1Settings.listFilter || {}).bop;
    const filterSet = (Array.isArray(lf) && lf.length > 0) ? new Set(lf) : null;
    const groups = {};
    items.forEach(it => { (groups[it._group] = groups[it._group] || []).push(it); });
    let html = '';
    for (const [grp, rows] of Object.entries(groups)) {
      html += `<div class="wb-p1-sp-group-hdr">${grp}</div>`;
      html += rows.map(it =>
        `<label class="wb-p1-sp-item wb-p1-list-item">
          <input type="checkbox" class="wb-p1-bop-cb" data-gid="${it.gid}"${filterSet ? (filterSet.has(it.gid) ? ' checked' : '') : ' checked'}>
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${it.name}</span>
        </label>`
      ).join('');
    }
    subEl.innerHTML = html;
    subEl.querySelectorAll('.wb-p1-bop-cb').forEach(cb => {
      cb.addEventListener('change', () => {
        const checked = [...subEl.querySelectorAll('.wb-p1-bop-cb:checked')].map(el => el.dataset.gid);
        if (!checked.length) { cb.checked = true; return; }
        const lf2 = (_p1Settings.listFilter = _p1Settings.listFilter || {});
        if (checked.length === items.length) {
          delete lf2.bop;
        } else {
          lf2.bop = checked;
        }
        _saveP1Settings();
        _scheduleP1Reload();
        const cnt = checked.length < items.length ? checked.length : 0;
        const domainRow = document.querySelector('.wb-p1-domain-row[data-domain="bop"]');
        let badge = domainRow?.querySelector('.wb-p1-filter-badge');
        if (cnt > 0) {
          if (!badge) {
            domainRow?.querySelector('label span:not(.wb-p1-filter-badge)')
              ?.insertAdjacentHTML('afterend', `<span class="wb-p1-filter-badge">${cnt}</span>`);
          } else { badge.textContent = cnt; }
        } else { badge?.remove(); }
      });
    });
  }

  function _renderP1ListCheckboxes(domain, lists, subEl) {
    if (!lists.length) {
      subEl.innerHTML = '<span class="wb-p1-sp-loading">暂无清单</span>';
      return;
    }
    const lf = (_p1Settings.listFilter || {})[domain];
    const filterSet = (Array.isArray(lf) && lf.length > 0) ? new Set(lf) : null;
    subEl.innerHTML = lists.map(l =>
      `<label class="wb-p1-sp-item wb-p1-list-item">
        <input type="checkbox" class="wb-p1-list-cb" data-domain="${domain}" data-gid="${_esc(l.gid)}"${filterSet ? (filterSet.has(l.gid) ? ' checked' : '') : ' checked'}>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${_esc(l.name)}</span>
      </label>`
    ).join('');

    subEl.querySelectorAll('.wb-p1-list-cb').forEach(cb => {
      cb.addEventListener('change', () => {
        const checked = [...subEl.querySelectorAll('.wb-p1-list-cb:checked')].map(el => el.dataset.gid);
        if (!checked.length) { cb.checked = true; return; }
        const lf2 = (_p1Settings.listFilter = _p1Settings.listFilter || {});
        if (checked.length === lists.length) {
          delete lf2[domain]; // 全选 → 无过滤
        } else {
          lf2[domain] = checked;
        }
        _saveP1Settings();
        _scheduleP1Reload();
        // 更新 badge
        const cnt = checked.length < lists.length ? checked.length : 0;
        const domainRow = document.querySelector(`.wb-p1-domain-row[data-domain="${domain}"]`);
        let badge = domainRow?.querySelector('.wb-p1-filter-badge');
        if (cnt > 0) {
          if (!badge) {
            const span = domainRow?.querySelector('label span:not(.wb-p1-filter-badge)');
            span?.insertAdjacentHTML('afterend', `<span class="wb-p1-filter-badge">${cnt}</span>`);
          } else { badge.textContent = cnt; }
        } else {
          badge?.remove();
        }
      });
    });
  }

  function _initP1SettingsPop() {
    const btn = document.getElementById('wb-p1-settings-btn');
    const pop = document.getElementById('wbP1SettingsPop');
    if (!btn || !pop) return;

    // 初始化 UI 值（非来源部分）
    const _syncNonSrcUI = () => {
      const sfSettings = _p1Settings.statusFilter || ['pending','progress','done','closed'];
      pop.querySelectorAll('.wb-p1-sf').forEach(cb => {
        cb.checked = sfSettings.includes(cb.value);
      });
      const gRad = pop.querySelector(`input[name="p1-group"][value="${_p1Settings.groupBy}"]`);
      if (gRad) gRad.checked = true;
      const sRad = pop.querySelector(`input[name="p1-sort"][value="${_p1Settings.sortBy}"]`);
      if (sRad) sRad.checked = true;
    };

    // 打开 / 关闭
    let _popOpen = false;
    let _outsideHandler = null;
    const _openPop = () => {
      _renderP1SrcSection(document.getElementById('wbP1SrcBody'));
      _syncNonSrcUI();
      const rect = btn.getBoundingClientRect();
      const pw = 220;
      let left = rect.right - pw;
      if (left < 4) left = 4;
      pop.style.left = left + 'px';
      pop.style.top  = (rect.bottom + 4) + 'px';
      pop.classList.remove('hidden');
      btn.classList.add('is-active');
      _popOpen = true;
      _outsideHandler = (e) => {
        if (!pop.contains(e.target) && !btn.contains(e.target)) _closePop();
      };
      setTimeout(() => document.addEventListener('click', _outsideHandler, true), 10);
    };
    const _closePop = () => {
      pop.classList.add('hidden');
      btn.classList.remove('is-active');
      _popOpen = false;
      if (_outsideHandler) {
        document.removeEventListener('click', _outsideHandler, true);
        _outsideHandler = null;
      }
    };

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      _popOpen ? _closePop() : _openPop();
    });

    // 状态筛选 checkbox
    pop.querySelectorAll('.wb-p1-sf').forEach(cb => {
      cb.addEventListener('change', () => {
        const checked = [...pop.querySelectorAll('.wb-p1-sf:checked')].map(el => el.value);
        if (!checked.length) { cb.checked = true; return; }
        _p1Settings.statusFilter = checked;
        _saveP1Settings();
        _renderPanelToday(_panelData[1] || []);
        if (_vis.cal) _renderCalendar();
      });
    });

    // 分组方式 radio
    pop.querySelectorAll('input[name="p1-group"]').forEach(r => {
      r.addEventListener('change', () => {
        if (!r.checked) return;
        _p1Settings.groupBy = r.value;
        _saveP1Settings();
        _renderPanelToday(_panelData[1] || []);
        if (_vis.cal) _renderCalendar();
      });
    });

    // 排序方式 radio
    pop.querySelectorAll('input[name="p1-sort"]').forEach(r => {
      r.addEventListener('change', () => {
        if (!r.checked) return;
        _p1Settings.sortBy = r.value;
        _saveP1Settings();
        _renderPanelToday(_panelData[1] || []);
        if (_vis.cal) _renderCalendar();
      });
    });
  }

  function _saveP1Settings() {
    localStorage.setItem(_lsk(_P1_SETTINGS_LS), JSON.stringify(_p1Settings));
  }

  // ── 面板2 设置浮层 ─────────────────────────────────────────────────────────
  function _initP2SettingsPop() {
    const btn = document.getElementById('wb-p2-settings-btn');
    const pop = document.getElementById('wbP2SettingsPop');
    if (!btn || !pop) return;

    // 同步大标题 checkbox 状态
    const _syncSecUI = () => {
      const hideSecs = _p2Settings.hideSecs || [];
      pop.querySelectorAll('.wb-p2-sec').forEach(cb => {
        cb.checked = !hideSecs.includes(cb.value);
      });
    };

    // 动态填充项目列表
    const _populateProjects = () => {
      const body = document.getElementById('wbP2SpProjects');
      if (!body) return;
      if (!_allProjects.length) {
        body.innerHTML = '<span class="wb-p1-sp-loading" style="padding:2px 4px;opacity:.5">暂无项目</span>';
        return;
      }
      const filterProjs = _p2Settings.filterProjects || [];
      body.innerHTML = _allProjects.map(p => `
        <label class="wb-p1-sp-item">
          <input type="checkbox" class="wb-p2-proj" value="${_esc(p.gid)}" ${filterProjs.includes(p.gid) ? 'checked' : ''}>
          <span>${_esc(p.name || p.gid)}</span>
        </label>`).join('');
      body.querySelectorAll('.wb-p2-proj').forEach(cb => {
        cb.addEventListener('change', () => {
          _p2Settings.filterProjects = [...body.querySelectorAll('.wb-p2-proj:checked')].map(el => el.value);
          _saveP2Settings();
          if (_treeSections) _renderP2TreeSections(_treeSections);
        });
      });
    };

    let _popOpen = false;
    let _outsideHandler = null;
    const _openPop = () => {
      _syncSecUI();
      _populateProjects();
      const rect = btn.getBoundingClientRect();
      const pw = 200;
      let left = rect.right - pw;
      if (left < 4) left = 4;
      pop.style.left = left + 'px';
      pop.style.top  = (rect.bottom + 4) + 'px';
      pop.classList.remove('hidden');
      btn.classList.add('is-active');
      _popOpen = true;
      _outsideHandler = e => {
        if (!pop.contains(e.target) && !btn.contains(e.target)) _closePop();
      };
      setTimeout(() => document.addEventListener('click', _outsideHandler, true), 10);
    };
    const _closePop = () => {
      pop.classList.add('hidden');
      btn.classList.remove('is-active');
      _popOpen = false;
      if (_outsideHandler) {
        document.removeEventListener('click', _outsideHandler, true);
        _outsideHandler = null;
      }
    };

    btn.addEventListener('click', e => { e.stopPropagation(); _popOpen ? _closePop() : _openPop(); });

    // 大标题 checkbox 变更
    pop.querySelectorAll('.wb-p2-sec').forEach(cb => {
      cb.addEventListener('change', () => {
        const hidden = [...pop.querySelectorAll('.wb-p2-sec:not(:checked)')].map(el => el.value);
        _p2Settings.hideSecs = hidden;
        _saveP2Settings();
        if (_treeSections) _renderP2TreeSections(_treeSections);
      });
    });
  }

  // ── 面板2 ＋ 新建文件 ─────────────────────────────────────────────────────

  const _WB_COLOR_PRESETS = ['#5b8dee','#22c55e','#ef4444','#f97316','#8b5cf6','#6b7280'];
  const _WB_FILE_TYPE_META = {
    list_task:      { label: '任务清单',   icon: 'task' },
    list_issue:     { label: '问题清单',   icon: 'issue' },
    list_knowledge: { label: '知识清单',   icon: 'knowledge' },
    list_rule:      { label: '规则清单',   icon: 'rule' },
    bop_version:    { label: 'BOP版本',    icon: 'bop' },
    pbom:           { label: 'PBOM版本',   icon: 'pbom' },
    doc_md:         { label: 'MD文档',     icon: 'md' },
    doc_richtext:   { label: '富文本文档', icon: 'richtext' },
    doc_url:        { label: '网页文件',   icon: 'url' },
    doc_pdf:        { label: 'PDF文件',    icon: 'pdf' },
  };
  const _WB_TYPE_BY_DOMAIN = {
    craft:     ['bop_version','pbom'],
    project:   ['list_task','list_issue'],
    knowledge: ['list_knowledge','list_rule','doc_md','doc_richtext','doc_url','doc_pdf'],
  };
  const _WB_DOMAIN_LABELS = { craft:'工艺规划', project:'项目管理', knowledge:'知识库' };

  let _wbCreateType = null;

  function _wbIconSvg(iconKey) {
    const icons = {
      task:      '<polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>',
      issue:     '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
      knowledge: '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>',
      rule:      '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>',
      bop:       '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
      pbom:      '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
      md:        '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/>',
      richtext:  '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/>',
      url:       '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>',
      pdf:       '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 13h1.5a1.5 1.5 0 000-3H9v6"/>',
    };
    const d = icons[iconKey] || icons.md;
    return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  }

  function _wbEscHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // 将平铺文件夹数组构建为带缩进的 <option> 字符串（树形 DFS，含个人及子文件夹）
  function _wbBuildFolderOptions(folders) {
    const childMap = {};
    const roots = [];
    for (const f of folders) {
      if (f.parent_gid) {
        (childMap[f.parent_gid] = childMap[f.parent_gid] || []).push(f);
      } else {
        roots.push(f);
      }
    }
    const sort = arr => arr.slice().sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.name || '').localeCompare(b.name || ''));
    let html = '<option value="">— 根目录 —</option>';
    function walk(node, depth) {
      const pad = '\u00a0\u00a0'.repeat(depth);
      html += `<option value="${node.gid}">${pad}${_wbEscHtml(node.name)}</option>`;
      for (const child of sort(childMap[node.gid] || [])) walk(child, depth + 1);
    }
    for (const root of sort(roots)) walk(root, 0);
    return html;
}

  function _initP2NewBtn() {
    const btn    = document.getElementById('wb-p2-new-btn');
    const picker = document.getElementById('wbTypePicker');
    if (!btn || !picker) return;

    // 渲染 type picker 内容
    let html = '';
    for (const [domain, types] of Object.entries(_WB_TYPE_BY_DOMAIN)) {
      html += `<div class="mf-tp-label">${_WB_DOMAIN_LABELS[domain]}</div>`;
      for (const ft of types) {
        const meta = _WB_FILE_TYPE_META[ft];
        html += `<button class="mf-tp-item" data-type="${ft}">
          <span class="mf-tp-icon">${_wbIconSvg(meta.icon)}</span>
          <span>${meta.label}</span>
        </button>`;
      }
    }
    picker.innerHTML = html;

    picker.addEventListener('click', e => {
      const item = e.target.closest('.mf-tp-item');
      if (!item) return;
      e.stopPropagation();
      picker.hidden = true;
      _openWbCreateModal(item.dataset.type);
    });

    btn.addEventListener('click', e => {
      picker.hidden = !picker.hidden;
      if (!picker.hidden) {
        const r = btn.getBoundingClientRect();
        picker.style.top  = (r.bottom + 4) + 'px';
        picker.style.left = Math.max(4, r.right - 180) + 'px';
      }
      e.stopPropagation();
    });

    document.addEventListener('click', () => { picker.hidden = true; });

    // modal 关闭
    document.getElementById('wbCreateModalClose')?.addEventListener('click', _closeWbModal);
    document.getElementById('wbCreateModalCancel')?.addEventListener('click', _closeWbModal);
    document.getElementById('wbCreateModalOverlay')?.addEventListener('click', e => {
      if (e.target.id === 'wbCreateModalOverlay') _closeWbModal();
    });
    document.getElementById('wbCreateModalSubmit')?.addEventListener('click', _handleWbSubmit);

    // 可见范围按钮组（事件委托）
    document.addEventListener('click', e => {
      const scopeBtn = e.target.closest('.mf-scope-btn');
      if (!scopeBtn) return;
      const group = scopeBtn.closest('.mf-scope-btns');
      if (!group) return;
      group.querySelectorAll('.mf-scope-btn').forEach(b => b.classList.remove('active'));
      scopeBtn.classList.add('active');
      const body = document.getElementById('wbCreateModalBody');
      const hiddenVis   = body?.querySelector('#wbFormVisibility');
      const hiddenScope = body?.querySelector('#wbFormScopeType');
      if (hiddenVis)   hiddenVis.value   = scopeBtn.dataset.value;
      if (hiddenScope) hiddenScope.value = scopeBtn.dataset.value;
      // 项目可见范围：展示/隐藏项目选择器
      const projectRow = body?.querySelector('#wbFormProjectRow');
      if (projectRow) projectRow.style.display = scopeBtn.dataset.value === 'project' ? '' : 'none';
    });
  }

  function _closeWbModal() {
    document.getElementById('wbCreateModalOverlay').hidden = true;
    _wbCreateType = null;
  }

  async function _openWbCreateModal(fileType) {
    _wbCreateType = fileType;
    const meta = _WB_FILE_TYPE_META[fileType] || {};
    document.getElementById('wbCreateModalIcon').innerHTML  = _wbIconSvg(meta.icon || 'md');
    document.getElementById('wbCreateModalTitle').textContent = '新建 ' + (meta.label || fileType);
    document.getElementById('wbCreateModalBody').innerHTML  = _buildWbForm(fileType);
    document.getElementById('wbCreateModalSubmit').disabled = (fileType === 'pbom');
    document.getElementById('wbCreateModalSubmit').textContent = '创建';
    document.getElementById('wbCreateModalOverlay').hidden  = false;

    // 模式 tab 切换
    document.querySelectorAll('#wbCreateModalBody .mf-mode-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const container = tab.closest('.mf-mode-tabs');
        container.querySelectorAll('.mf-mode-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const prefix = fileType === 'bop_version' ? 'wbBopPanel' : 'wbPbomPanel';
        document.querySelectorAll('[id^="' + prefix + '"]').forEach(p => { p.hidden = true; });
        const panelId = prefix + tab.dataset.mode.charAt(0).toUpperCase() + tab.dataset.mode.slice(1);
        const panel = document.getElementById(panelId);
        if (panel) panel.hidden = false;
      });
    });

    const fn = _cf();
    const needProjects = fileType.startsWith('list_') || fileType === 'bop_version';
    const needFolders  = fileType.startsWith('doc_');
    const needVersions = fileType === 'bop_version';

    const [projRes, folderRes, verRes] = await Promise.allSettled([
      (needProjects && fn) ? fn('/api/projects') : Promise.resolve(null),
      (needFolders  && fn) ? fn('/api/knowledge_hub/folders') : Promise.resolve(null),
      (needVersions && fn) ? fn('/api/bop/versions') : Promise.resolve(null),
    ]);

    if (needProjects && projRes.status === 'fulfilled' && projRes.value) {
      const arr = Array.isArray(projRes.value) ? projRes.value : (projRes.value.data || projRes.value.projects || []);
      const opts = '<option value="">— 不关联项目 —</option>' +
        arr.map(p => `<option value="${p.gid}">${_wbEscHtml(p.name)}</option>`).join('');
      document.querySelectorAll('#wbCreateModalBody .mf-proj-select').forEach(sel => { sel.innerHTML = opts; });
    }

    if (needFolders && folderRes.status === 'fulfilled' && folderRes.value) {
      const arr = Array.isArray(folderRes.value) ? folderRes.value : (folderRes.value.data || folderRes.value.folders || []);
      document.querySelectorAll('#wbCreateModalBody .mf-folder-select').forEach(sel => { sel.innerHTML = _wbBuildFolderOptions(arr); });
    }

    if (needVersions && verRes.status === 'fulfilled' && verRes.value) {
      const arr = Array.isArray(verRes.value) ? verRes.value : (verRes.value.data || verRes.value.versions || []);
      const opts = '<option value="">— 选择源版本 —</option>' +
        arr.map(v => `<option value="${v.gid}">${_wbEscHtml((v.bop_name||'') + ' ' + (v.version_tag||''))}</option>`).join('');
      ['wbFormForkSrc','wbFormSmartSrc'].forEach(id => {
        const sel = document.getElementById(id);
        if (sel) sel.innerHTML = opts;
      });
    }

    document.getElementById('wbPbomGotoEbom')?.addEventListener('click', () => {
      _closeWbModal();
      window.top?.TabManager?.open('ebom');
    });

    document.getElementById('wbFormFilePickBtn')?.addEventListener('click', async () => {
      const result = await window.electronAPI?.showOpenDialog?.({
        properties: ['openFile'], filters: [{ name: 'PDF', extensions: ['pdf'] }],
      });
      if (result?.filePaths?.[0]) document.getElementById('wbFormFilePath').value = result.filePaths[0];
    });

    document.getElementById('wbColorPicker')?.addEventListener('click', e => {
      const swatch = e.target.closest('.mf-color-swatch');
      if (!swatch) return;
      document.querySelectorAll('#wbColorPicker .mf-color-swatch').forEach(s => s.classList.remove('selected'));
      swatch.classList.add('selected');
      const ci = document.getElementById('wbFormColor');
      const ni = document.getElementById('wbColorNative');
      if (ci) ci.value = swatch.dataset.color;
      if (ni) ni.value = swatch.dataset.color;
    });
    document.getElementById('wbColorNative')?.addEventListener('input', e => {
      document.querySelectorAll('#wbColorPicker .mf-color-swatch').forEach(s => s.classList.remove('selected'));
      const ci = document.getElementById('wbFormColor');
      if (ci) ci.value = e.target.value;
    });

    setTimeout(() => document.querySelector('#wbCreateModalBody input:not([type="hidden"]):not([type="color"])')?.focus(), 50);
  }

  function _buildWbForm(fileType) {
    if (fileType.startsWith('list_')) return _buildWbFormList(fileType.replace('list_',''));
    if (fileType === 'bop_version')   return _buildWbFormBop();
    if (fileType === 'pbom')          return _buildWbFormPbom();
    if (fileType.startsWith('doc_'))  return _buildWbFormDoc(fileType);
    return '<p>不支持的类型</p>';
  }

  function _buildWbFormList(itemType) {
    const swatches = _WB_COLOR_PRESETS.map((c, i) =>
      `<span class="mf-color-swatch${i===0?' selected':''}" data-color="${c}" style="background:${c}"></span>`
    ).join('');
    const projRow = `
      <div id="wbFormProjectRow" style="display:none">
        <label class="mf-form-label" style="margin-top:12px">关联项目 <span style="color:#ef4444">*</span></label>
        <select class="mf-form-input mf-proj-select" id="wbFormProject"><option value="">— 加载中… —</option></select>
      </div>`;
    return `
      <label class="mf-form-label">清单名称 <span style="color:#ef4444">*</span></label>
      <input class="mf-form-input" id="wbFormName" type="text" placeholder="输入清单名称…" autocomplete="off">
      <label class="mf-form-label" style="margin-top:12px">颜色</label>
      <div class="mf-color-picker" id="wbColorPicker">${swatches}
        <input class="mf-color-native" id="wbColorNative" type="color" value="${_WB_COLOR_PRESETS[0]}">
      </div>
      <input type="hidden" id="wbFormColor" value="${_WB_COLOR_PRESETS[0]}">
      ${projRow}
      <label class="mf-form-label" style="margin-top:12px">可见范围</label>
      <div class="mf-scope-btns">
        <button type="button" class="mf-scope-btn" data-value="private">私人</button>
        <button type="button" class="mf-scope-btn" data-value="project">项目</button>
        <button type="button" class="mf-scope-btn active" data-value="team">团队</button>
        <button type="button" class="mf-scope-btn" data-value="public">公开</button>
      </div>
      <input type="hidden" id="wbFormVisibility" value="team">`;
  }

  function _buildWbFormBop() {
    return `
      <div class="mf-mode-tabs" id="wbBopModeTabs">
        <button class="mf-mode-tab active" data-mode="blank">空白新建</button>
        <button class="mf-mode-tab" data-mode="fork">Fork 版本</button>
        <button class="mf-mode-tab" data-mode="smart">Smart Fork</button>
      </div>
      <div class="mf-mode-panel" id="wbBopPanelBlank">
        <label class="mf-form-label">版本标签 <span style="color:#ef4444">*</span></label>
        <input class="mf-form-input" id="wbFormVersionTag" type="text" placeholder="例：V1.0" autocomplete="off">
        <label class="mf-form-label" style="margin-top:12px">BOP 名称</label>
        <input class="mf-form-input" id="wbFormBopName" type="text" placeholder="可选" autocomplete="off">
        <label class="mf-form-label" style="margin-top:12px">关联项目（可选）</label>
        <select class="mf-form-input mf-proj-select" id="wbFormBopProject"><option value="">— 加载中… —</option></select>
        <label class="mf-form-label" style="margin-top:12px">节拍时间（秒）</label>
        <input class="mf-form-input" id="wbFormTaktTime" type="number" value="60" min="1">
      </div>
      <div class="mf-mode-panel" id="wbBopPanelFork" hidden>
        <label class="mf-form-label">源版本 <span style="color:#ef4444">*</span></label>
        <select class="mf-form-input" id="wbFormForkSrc"><option value="">— 加载中… —</option></select>
        <label class="mf-form-label" style="margin-top:12px">新版本标签 <span style="color:#ef4444">*</span></label>
        <input class="mf-form-input" id="wbFormForkTag" type="text" placeholder="例：V2.0" autocomplete="off">
        <label class="mf-form-label" style="margin-top:12px">变更说明（可选）</label>
        <input class="mf-form-input" id="wbFormForkNote" type="text" placeholder="">
      </div>
      <div class="mf-mode-panel" id="wbBopPanelSmart" hidden>
        <label class="mf-form-label">源版本 <span style="color:#ef4444">*</span></label>
        <select class="mf-form-input" id="wbFormSmartSrc"><option value="">— 加载中… —</option></select>
        <label class="mf-form-label" style="margin-top:12px">模式</label>
        <select class="mf-form-input" id="wbFormSmartMode">
          <option value="minor_facelift">小改款</option>
          <option value="new_model">新车型</option>
        </select>
        <label class="mf-form-label" style="margin-top:12px">新版本标签 <span style="color:#ef4444">*</span></label>
        <input class="mf-form-input" id="wbFormSmartTag" type="text" placeholder="例：V3.0" autocomplete="off">
      </div>`;
  }

  function _buildWbFormPbom() {
    return `
      <div style="padding:12px 0;color:var(--wb-text-2,#888);font-size:12.5px;line-height:1.6">
        PBOM 版本通过 Excel 导入创建，请前往 EBOM 页面完成导入操作。
      </div>
      <button class="mf-btn-secondary" id="wbPbomGotoEbom" style="width:100%;margin-top:4px">前往 EBOM 页面 →</button>`;
  }

  function _buildWbFormDoc(fileType) {
    let extra = '';
    if (fileType === 'doc_url') {
      extra = `<label class="mf-form-label" style="margin-top:12px">URL <span style="color:#ef4444">*</span></label>
        <input class="mf-form-input" id="wbFormUrl" type="url" placeholder="https://…">`;
    } else if (fileType === 'doc_pdf') {
      extra = `<label class="mf-form-label" style="margin-top:12px">文件路径 <span style="color:#ef4444">*</span></label>
        <div style="display:flex;gap:6px">
          <input class="mf-form-input" id="wbFormFilePath" type="text" placeholder="选择 PDF…" readonly style="flex:1">
          <button class="mf-btn-secondary" id="wbFormFilePickBtn" style="flex-shrink:0;padding:4px 10px">选择…</button>
        </div>`;
    } else if (fileType === 'doc_md') {
      extra = `<label class="mf-form-label" style="margin-top:12px">初始内容（可选）</label>
        <textarea class="mf-form-input mf-form-textarea" id="wbFormContent" rows="4" placeholder="支持 Markdown…"></textarea>`;
    }
    const isUrl = fileType === 'doc_url';
    return `
      <label class="mf-form-label">标题${isUrl ? '（可选）' : ' <span style="color:#ef4444">*</span>'}</label>
      <input class="mf-form-input" id="wbFormTitle" type="text" placeholder="输入标题…" autocomplete="off">
      ${extra}
      <label class="mf-form-label" style="margin-top:12px">文件夹（可选）</label>
      <select class="mf-form-input mf-folder-select" id="wbFormFolder"><option value="">— 根目录 —</option></select>
      <label class="mf-form-label" style="margin-top:12px">可见范围</label>
      <div class="mf-scope-btns">
        <button type="button" class="mf-scope-btn" data-value="personal">个人</button>
        <button type="button" class="mf-scope-btn" data-value="team">团队</button>
        <button type="button" class="mf-scope-btn active" data-value="public">公开</button>
      </div>
      <input type="hidden" id="wbFormScopeType" value="public">`;
  }

  async function _handleWbSubmit() {
    const btn = document.getElementById('wbCreateModalSubmit');
    btn.disabled = true;
    btn.textContent = '创建中…';
    try {
      const result = await _doWbCreate(_wbCreateType);
      if (result) {
        _closeWbModal();
        // 刷新面板2文件树
        _renderP2Tree();
        // 在面板3打开
        _openListInP3({
          gid:       result.gid,
          name:      result.name || result.title || '',
          title:     result.name || result.title || '',
          item_type: result.item_type,
        });
      }
    } catch (err) {
      _showWbToast('创建失败：' + (err.message || '未知错误'), 'error');
      btn.disabled = false;
      btn.textContent = '创建';
    }
  }

  async function _doWbCreate(fileType) {
    const fn = _cf();
    if (!fn) throw new Error('未登录');

    if (fileType.startsWith('list_')) {
      const name       = document.getElementById('wbFormName')?.value?.trim();
      const color      = document.getElementById('wbFormColor')?.value || '#5b8dee';
      const visibility = document.getElementById('wbFormVisibility')?.value || 'team';
      const projectGid = document.getElementById('wbFormProject')?.value || null;
      if (!name) { _showWbToast('请输入清单名称'); return null; }
      if (visibility === 'project' && !projectGid) { _showWbToast('请选择关联项目'); return null; }
      const itemType = fileType.replace('list_', '');
      const uid = _currentUser?.gid || '';
      const body = { name, color, item_type: itemType, visibility, storage_scope: 'cloud', owner_type: 'user', owner_gid: uid };
      if (projectGid) body.project_gid = projectGid;
      const res = await fn('/api/lists', { method: 'POST', body: JSON.stringify(body) });
      const gid = res?.data?.gid || res?.gid;
      return { gid, name, item_type: itemType };
    }

    if (fileType === 'bop_version') {
      const mode = document.querySelector('#wbBopModeTabs .mf-mode-tab.active')?.dataset.mode || 'blank';
      if (mode === 'blank') {
        const versionTag = document.getElementById('wbFormVersionTag')?.value?.trim();
        const bopName    = document.getElementById('wbFormBopName')?.value?.trim() || '';
        const projectGid = document.getElementById('wbFormBopProject')?.value || null;
        const taktTime   = parseFloat(document.getElementById('wbFormTaktTime')?.value) || 60;
        if (!versionTag) { _showWbToast('请填写版本标签'); return null; }
        const body = { version_tag: versionTag, bop_name: bopName, takt_time: taktTime };
        if (projectGid) body.project_gid = projectGid;
        const res = await fn('/api/bop/versions', { method: 'POST', body: JSON.stringify(body) });
        const gid = res?.data?.gid || res?.gid;
        return { gid, name: bopName || versionTag, item_type: 'bop_version' };
      }
      if (mode === 'fork') {
        const srcGid = document.getElementById('wbFormForkSrc')?.value;
        const tag    = document.getElementById('wbFormForkTag')?.value?.trim();
        const note   = document.getElementById('wbFormForkNote')?.value?.trim() || null;
        if (!srcGid || !tag) { _showWbToast('请选择源版本并填写新版本标签'); return null; }
        const res = await fn(`/api/bop/versions/${srcGid}/fork`, { method: 'POST', body: JSON.stringify({ target_version_tag: tag, change_note: note }) });
        const gid = res?.data?.gid || res?.gid;
        return { gid, name: tag, item_type: 'bop_version' };
      }
      if (mode === 'smart') {
        const srcGid = document.getElementById('wbFormSmartSrc')?.value;
        const m      = document.getElementById('wbFormSmartMode')?.value;
        const tag    = document.getElementById('wbFormSmartTag')?.value?.trim();
        if (!srcGid || !tag) { _showWbToast('请选择源版本并填写标签'); return null; }
        const res = await fn(`/api/bop/versions/${srcGid}/smart-fork`, { method: 'POST', body: JSON.stringify({ mode: m, target_version_tag: tag }) });
        const gid = res?.data?.gid || res?.gid;
        return { gid, name: tag, item_type: 'bop_version' };
      }
    }

    if (fileType === 'pbom') {
      const mode = document.querySelector('#wbPbomModeTabs .mf-mode-tab.active')?.dataset.mode || 'blank';
      if (mode === 'import') return null;
      const name = document.getElementById('wbFormPbomName')?.value?.trim();
      if (!name) { _showWbToast('请填写版本名称'); return null; }
      const res = await fn('/api/ebom/snapshots', { method: 'POST', body: JSON.stringify({ name, version_tag: name, source_type: 'manual' }) });
      const gid = res?.data?.gid || res?.gid;
      return { gid, name, item_type: 'pbom' };
    }

    if (fileType.startsWith('doc_')) {
      const docTypeMap = { doc_md: 'markdown', doc_richtext: 'richtext', doc_url: 'url', doc_pdf: 'pdf' };
      const itemType  = docTypeMap[fileType];
      const scopeType = document.getElementById('wbFormScopeType')?.value || 'public';
      const folderGid = document.getElementById('wbFormFolder')?.value || null;
      let title = document.getElementById('wbFormTitle')?.value?.trim() || '';
      const body = { item_type: itemType, scope_type: scopeType };
      if (folderGid) body.folder_gid = folderGid;
      if (fileType === 'doc_url') {
        const url = document.getElementById('wbFormUrl')?.value?.trim() || '';
        if (!url) { _showWbToast('请输入 URL'); return null; }
        body.content_ref = url;
        if (!title) { try { title = new URL(url).hostname; } catch { title = url.slice(0, 40); } }
      } else if (fileType === 'doc_pdf') {
        const fp = document.getElementById('wbFormFilePath')?.value?.trim() || '';
        if (!fp) { _showWbToast('请选择 PDF 文件'); return null; }
        if (!title) { _showWbToast('请输入标题'); return null; }
        body.content_ref = fp;
      } else if (fileType === 'doc_md') {
        if (!title) { _showWbToast('请输入标题'); return null; }
        body.content_md = document.getElementById('wbFormContent')?.value || '';
      } else {
        if (!title) { _showWbToast('请输入标题'); return null; }
      }
      body.title = title || '未命名';
      const res = await fn('/api/knowledge_hub/items', { method: 'POST', body: JSON.stringify(body) });
      const gid = res?.gid || res?.data?.gid;
      return { gid, name: body.title, item_type: fileType };
    }

    return null;
  }

  function _showWbToast(msg, type = 'info') {
    const t = Object.assign(document.createElement('div'), {
      className: 'mf-toast' + (type === 'error' ? ' error' : ''),
      textContent: msg,
    });
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  // 防抖重新加载（来源变更时延迟 300ms 再请求）
  function _scheduleP1Reload() {
    clearTimeout(_p1ReloadTimer);
    _p1ReloadTimer = setTimeout(() => _loadPanel1(), 300);
  }


  async function _renderPanelList() {
    const tlsEl   = document.getElementById('wb-p1-tls');
    const todayEl = document.getElementById('wb-p1-today');
    if (!tlsEl) return;

    // 切换子容器：隐藏 today，显示 TLS
    if (todayEl) todayEl.style.display = 'none';
    tlsEl.style.display = '';

    const fn = _cf();
    if (!fn) { tlsEl.innerHTML = '<div class="wb-empty">请先登录</div>'; return; }

    const m = _getActiveTabMode();

    // 全部类型 → TreeListShell
    const cols    = WB_P1_COLS_MAP[m.itemType]   || WB_P1_COLS_TASK;
    const apiFn   = WB_P1_API_MAP[m.itemType];
    const url     = apiFn ? apiFn(m.listGid) : `/api/tasks?list_gid=${m.listGid}&limit=200`;

    try {
      const res = await fn(url);
      _p1TlsData = Array.isArray(res) ? res : (res.items || res.data || []);
      // 补充 item_type，供详情条判断类型（各 API 原始响应不含此字段）
      _p1TlsData.forEach(row => { if (!row.item_type) row.item_type = m.itemType; });
    } catch (e) {
      console.error('清单加载失败', e);
      _p1TlsData = [];
    }

    // BOP entries API 因 JOIN 会产生重复行（同一 gid 对应多条 primary link），去重
    if (m.itemType === 'bop_version') {
      const seen = new Set();
      _p1TlsData = _p1TlsData.filter(r => { if (seen.has(r.gid)) return false; seen.add(r.gid); return true; });
    }

    // itemType 或 listGid 变了 → 销毁旧实例，重建
    const tlsKey = m.itemType + ':' + (m.listGid || '');
    if (_p1Tls && _p1TlsItemType !== tlsKey) {
      tlsEl.innerHTML = '';
      _p1Tls = null;
    }

    if (!_p1Tls) {
      _p1TlsItemType = tlsKey;
      _p1Tls = new TreeListShell({
        mountEl:          tlsEl,
        forcedItemType:   m.itemType,
        listGid:          m.listGid || 'wb_fixed',   // 必须非空，否则 _loadData() 直接返回
        showListSelector: false,
        compactToolbar:   true,
        columns:          cols.filter(c => c.defaultOn !== false),
        allColumns:       cols,
        parentField:      WB_P1_PARENT_MAP[m.itemType] || null,
        groupField:       WB_P1_GROUP_MAP[m.itemType]  || null,
        moduleId:         'wb_p1_' + m.itemType,
        onLoadLists:      () => [],
        onLoadData:       () => _p1TlsData,
        onRowClick:       (row) => { _renderPanelDetail(row, 'p1'); _loadItemLinks(row); },
        detailMode:       'readonly',
        autoFitColumns:   true,   // 面板宽度变化时自动增减显示列
      });
      await _p1Tls.init();
    } else {
      await _p1Tls.refresh();
    }
    _setCount(1, _p1TlsData.length, _p1TlsData.length);
  }


  // ── 清单选择器 ────────────────────────────────────────────────────────────
  let _lpActiveIdx = -1;
  let _lpItems = [];   // 当前显示的选项 [{type:'today'}|{type:'list', ...}]

  function _openListPicker() {
    const picker = document.getElementById('wb-list-picker');
    if (!picker) return;
    _lpActiveIdx = -1;
    picker.classList.remove('hidden');
    const input = document.getElementById('wb-lp-input');
    if (input) { input.value = ''; input.focus(); }
    _renderListPickerItems('');
    // 关闭：点外面
    const closeOnOutside = (e) => {
      const panel = document.getElementById('wb-panel-1');
      if (!panel?.contains(e.target)) {
        _closeListPicker();
        document.removeEventListener('mousedown', closeOnOutside);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', closeOnOutside), 10);
  }

  function _closeListPicker() {
    document.getElementById('wb-list-picker')?.classList.add('hidden');
    _lpActiveIdx = -1;
  }

  async function _renderListPickerItems(query) {
    const listEl = document.getElementById('wb-lp-list');
    if (!listEl) return;

    // 先加载清单（有缓存直接用）
    if (!_panel1ListsCache) {
      listEl.innerHTML = '<div class="wb-lp-loading">加载中…</div>';
      _panel1ListsCache = await _fetchAllLists();
    }

    const q = query.toLowerCase();
    const todayMatch = !q || '今日清单'.includes(q) || 'today'.includes(q);

    _lpItems = [];
    if (todayMatch) _lpItems.push({ type: 'today', label: '今日清单' });

    const TYPE_LABEL = { task: '任务清单', issue: '问题清单', knowledge: '知识清单', knowledge_doc: '知识文档', rule: '规则清单', bop_version: 'BOP 版本', pbom: 'PBOM 版本' };
    const TYPE_ICON  = {
      task:        `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="2" width="12" height="12" rx="2"/><polyline points="5,8 7,10 11,6" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
      issue:       `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6"/><line x1="8" y1="5" x2="8" y2="9" stroke-linecap="round"/><circle cx="8" cy="11.5" r=".6" fill="currentColor"/></svg>`,
      knowledge:     `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 2h8a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z"/><line x1="5" y1="6" x2="11" y2="6" stroke-linecap="round"/><line x1="5" y1="9" x2="9" y2="9" stroke-linecap="round"/></svg>`,
      knowledge_doc: `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 2h6l3 3v9a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z"/><polyline points="10,2 10,5 13,5" stroke-linejoin="round"/></svg>`,
      rule:        `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><polygon points="8,2 14,5 14,11 8,14 2,11 2,5"/><line x1="8" y1="6" x2="8" y2="9" stroke-linecap="round"/><circle cx="8" cy="11" r=".6" fill="currentColor"/></svg>`,
      bop_version: `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="7" width="4" height="7"/><rect x="6" y="4" width="4" height="10"/><rect x="10" y="1" width="4" height="13"/></svg>`,
      pbom:        `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 3h12M2 8h8M2 13h5" stroke-linecap="round"/><circle cx="13" cy="11" r="2.5"/><line x1="13" y1="8.5" x2="13" y2="9" stroke-linecap="round"/></svg>`,
      _today:      `<svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1l1.8 4.4H15l-4.3 3.1 1.6 4.9L8 10.7l-4.3 2.7 1.6-4.9L1 5.4h5.2z"/></svg>`,
    };

    // 按 item_type 分组，组内按 name 过滤
    const groups = {};
    (_panel1ListsCache || []).forEach(l => {
      const name = l.name || '';
      if (q && !name.toLowerCase().includes(q)) return;
      const t = l.item_type || 'task';
      if (!groups[t]) groups[t] = [];
      groups[t].push({ type: 'list', listGid: l.gid, listTitle: l.name, itemType: t });
    });
    Object.values(groups).flat().forEach(opt => _lpItems.push(opt));

    if (!_lpItems.length) {
      listEl.innerHTML = '<div class="wb-lp-loading">无匹配</div>';
      return;
    }

    const isCurrent = (opt) => {
      if (opt.type === 'today') return _p1Tabs.some(t => t.type === 'today');
      return _p1Tabs.some(t => t.type === 'list' && t.listGid === opt.listGid);
    };

    // 统一用 _lpItems 数组索引渲染
    let html = '';
    let prevSection = '';
    _lpItems.forEach((opt, idx) => {
      const section = opt.type === 'today' ? '' : (TYPE_LABEL[opt.itemType] || opt.itemType);
      if (section && section !== prevSection) {
        html += `<div class="wb-lp-section-hdr">${section}</div>`;
        prevSection = section;
      }
      const icon = opt.type === 'today' ? TYPE_ICON._today : (TYPE_ICON[opt.itemType] || TYPE_ICON.task);
      const cur  = isCurrent(opt);
      const cls  = ['wb-lp-item', cur ? 'wb-lp-current' : '', idx === _lpActiveIdx ? 'wb-lp-active' : ''].filter(Boolean).join(' ');
      html += `<div class="${cls}" data-lp-idx="${idx}">${icon}<span class="wb-lp-item-name">${_esc(opt.label || opt.listTitle)}</span></div>`;
    });
    listEl.innerHTML = html;
    listEl.querySelectorAll('.wb-lp-item').forEach(el => {
      el.addEventListener('click', () => _selectListPickerItem(+el.dataset.lpIdx));
    });
  }

  function _selectListPickerItem(idx) {
    if (idx < 0 || idx >= _lpItems.length) return;
    const opt = _lpItems[idx];
    _closeListPicker();
    _addP1Tab(opt);
  }

  let _khPersonalFolders = [];   // 个人知识库文件夹
  let _khPersonalDocs    = [];   // 个人知识库文档

  async function _fetchAllLists() {
    const fn = _cf();
    if (!fn) return [];
    try {
      const [listsRes, bopRes, knowledgeRes, foldersRes, projectsRes,
             personalFoldersRes, personalDocsRes] = await Promise.allSettled([
        fn('/api/lists'),
        fn('/api/bop/versions'),
        fn('/api/knowledge_hub/items?scope_type=public'),
        fn('/api/knowledge_hub/folders?scope_type=public'),
        fn('/api/projects'),
        fn('/api/knowledge_hub/folders?scope_type=personal'),
        fn('/api/knowledge_hub/items?scope_type=personal'),
      ]);
      const lists = listsRes.status === 'fulfilled'
        ? (listsRes.value?.lists || listsRes.value?.data || listsRes.value || [])
        : [];
      const bops = bopRes.status === 'fulfilled'
        ? (bopRes.value?.versions || bopRes.value?.data || bopRes.value || []).map(r => ({
            ...r,
            name:      r.bop_name || r.name || r.version_name || r.gid,
            item_type: 'bop_version',
          }))
        : [];
      const docs = knowledgeRes.status === 'fulfilled'
        ? (knowledgeRes.value?.items || knowledgeRes.value?.data || knowledgeRes.value || []).map(r => ({
            ...r,
            name:      r.title || r.name || r.gid,
            item_type: 'knowledge_doc',
          }))
        : [];
      // 公共知识库文件夹
      _khFolders = foldersRes.status === 'fulfilled'
        ? (foldersRes.value?.folders || foldersRes.value?.data || foldersRes.value || [])
        : [];
      // 个人知识库文件夹 & 文档
      _khPersonalFolders = personalFoldersRes.status === 'fulfilled'
        ? (personalFoldersRes.value?.folders || personalFoldersRes.value?.data || personalFoldersRes.value || [])
        : [];
      _khPersonalDocs = personalDocsRes.status === 'fulfilled'
        ? (personalDocsRes.value?.items || personalDocsRes.value?.data || personalDocsRes.value || []).map(r => ({
            ...r,
            name:      r.title || r.name || r.gid,
            item_type: 'knowledge_doc',
          }))
        : [];
      // 存储项目列表供项目文件区渲染使用
      _allProjects = projectsRes.status === 'fulfilled'
        ? (projectsRes.value?.data || projectsRes.value?.projects || projectsRes.value || [])
        : [];
      return [...lists, ...bops, ...docs, ..._khPersonalDocs];
    } catch { return []; }
  }

  function _bindListPickerInput() {
    const input = document.getElementById('wb-lp-input');
    if (!input) return;
    input.addEventListener('input', () => _renderListPickerItems(input.value.trim()));
    input.addEventListener('keydown', e => {
      const picker = document.getElementById('wb-list-picker');
      if (picker?.classList.contains('hidden')) return;
      if (e.key === 'Escape') { e.stopPropagation(); _closeListPicker(); return; }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        _lpActiveIdx = Math.min(_lpActiveIdx + 1, _lpItems.length - 1);
        _highlightLpItem();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        _lpActiveIdx = Math.max(_lpActiveIdx - 1, 0);
        _highlightLpItem();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        _selectListPickerItem(_lpActiveIdx >= 0 ? _lpActiveIdx : 0);
      }
    });
  }

  function _highlightLpItem() {
    const listEl = document.getElementById('wb-lp-list');
    if (!listEl) return;
    listEl.querySelectorAll('.wb-lp-item').forEach((el, i) => {
      el.classList.toggle('wb-lp-active', i === _lpActiveIdx);
      if (i === _lpActiveIdx) el.scrollIntoView({ block: 'nearest' });
    });
  }

  // 切换详情条展开/折叠
  function _toggleDetailStrip(target) {
    const isP1 = (target === 'p1');
    if (isP1) { _p1DetailOpen = !_p1DetailOpen; } else { _p3DetailOpen = !_p3DetailOpen; }
    const pfx    = isP1 ? 'wb-p1' : 'wb-p3';
    const strip  = document.getElementById(`${pfx}-detail`);
    const isOpen = isP1 ? _p1DetailOpen : _p3DetailOpen;
    strip?.classList.toggle('is-open', isOpen);
    // 打开时渲染当前条目；关闭时不需要额外操作
    if (isOpen) {
      const item = isP1 ? _p1DetailItem : _p3DetailItem;
      _doRenderDetailContent(item, pfx);
    }
  }

  // ── 知识文档内联渲染 ────────────────────────────────────────────────────────
  function _renderKnowledgeDocPanel(el, item) {
    const md      = item.content_md || '';
    const tags    = (item.tags || []);
    const dateStr = item.updated_at
      ? new Date(item.updated_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
      : '';

    const tagsHtml = tags.map(t => `<span class="wb-kd-tag">${_esc(t)}</span>`).join('');
    const isEmbed  = item.item_type === 'weblink' || item.item_type === 'site_page';

    let contentHtml;
    if (item.item_type === 'weblink') {
      const url = item.url || '';
      contentHtml = url
        ? `<iframe src="${_esc(url)}" style="width:100%;flex:1;border:none;min-height:0;display:block"
             sandbox="allow-scripts allow-same-origin allow-forms allow-popups" allowfullscreen></iframe>`
        : '<div class="wb-empty">无链接</div>';
    } else if (item.item_type === 'site_page') {
      const ref  = typeof item.site_ref === 'string' ? JSON.parse(item.site_ref || '{}') : (item.site_ref || {});
      const path = ref?.path || item.file_path || '';
      contentHtml = path
        ? `<iframe src="${_esc('../' + path)}" style="width:100%;flex:1;border:none;min-height:0;display:block" allowfullscreen></iframe>`
        : '<div class="wb-empty">无页面路径</div>';
    } else if (md) {
      const rendered = window.marked
        ? marked.parse(md)
        : `<pre style="white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:12px">${_esc(md)}</pre>`;
      contentHtml = `<div class="wb-kd-body">${rendered}</div>`;
    } else {
      contentHtml = '<div class="wb-empty" style="margin-top:32px">暂无内容</div>';
    }

    // iframe 类型去掉内边距，让嵌入页面充满整个内容区
    const contentStyle = isEmbed ? 'style="padding:0;overflow:hidden"' : '';

    el.innerHTML = `
      <div class="wb-kd-wrap">
        <div class="wb-kd-header">
          <div class="wb-kd-title">${_esc(item.title || '未命名')}</div>
          <div class="wb-kd-meta">
            ${tagsHtml}
            ${dateStr ? `<span class="wb-kd-date">${dateStr}</span>` : ''}
          </div>
        </div>
        <div class="wb-kd-content" ${contentStyle}>${contentHtml}</div>
      </div>`;
  }

  // 详情条（选中行后在对应面板底部更新内容）
  // target: 'p1' = 面板1下方，'p3'（默认）= 面板3下方
  // 只存储 item，仅在对应详情条已展开时才渲染；不自动打开
  function _renderPanelDetail(item, target) {
    const isP1 = (target === 'p1');
    if (isP1) { _p1DetailItem = item; } else { _p3DetailItem = item; }
    const isOpen = isP1 ? _p1DetailOpen : _p3DetailOpen;
    if (!isOpen) return;
    _doRenderDetailContent(item, isP1 ? 'wb-p1' : 'wb-p3');
  }

  // 实际渲染详情内容（供切换打开和行点击两路复用）
  function _doRenderDetailContent(item, pfx) {
    const titleEl = document.getElementById(`${pfx}-detail-title`);
    const body    = document.getElementById(`${pfx}-detail-body`);
    if (!body) return;
    if (!item) {
      if (titleEl) titleEl.textContent = '';
      body.innerHTML = '<div style="color:var(--text-faint);font-size:12px;padding:2px 0">暂无选中条目</div>';
      return;
    }

    const type = item.item_type || 'task';
    const cols = WB_P1_COLS_MAP[type] || WB_P1_COLS_TASK;
    const typeLabels = { task:'任务', issue:'问题', bop_version:'BOP条目',
                         pbom:'PBOM零件', knowledge:'知识条目', rule:'规则' };

    // 可编辑字段规格（只有 task / issue）
    const _sel = (field, val, opts, labelMap) =>
      `<select class="wb-detail-inp" data-field="${field}">${
        opts.map(o => `<option value="${o}"${o===val?' selected':''}>${labelMap[o]||o}</option>`).join('')
      }</select>`;
    const _date = (field, val) =>
      `<input class="wb-detail-inp" type="date" data-field="${field}" value="${(val||'').substring(0,10)}">`;

    const taskStatuses  = ['pending','in_progress','done','cancelled'];
    const issueStatuses = ['open','in_progress','resolved','closed'];
    const statusLabel   = { pending:'待办', in_progress:'进行中', done:'完成', completed:'完成',
                            cancelled:'已取消', open:'待处理', resolved:'已解决', closed:'已关闭' };
    const prioValues    = ['urgent','high','medium','low'];
    const prioLabel     = { urgent:'紧急', high:'高', medium:'中', low:'低' };
    const sevValues     = ['critical','high','medium','low','info'];
    const sevLabel      = { critical:'严重', high:'高', medium:'中', low:'低', info:'提示' };

    const editableSpecs = {
      task: {
        status:         (v) => _sel('status',         v, taskStatuses,  statusLabel),
        priority:       (v) => _sel('priority',       v, prioValues,    prioLabel),
        due_date:       (v) => _date('due_date',       v),
        scheduled_date: (v) => _date('scheduled_date', v),
      },
      issue: {
        status:   (v) => _sel('status',   v, issueStatuses, statusLabel),
        severity: (v) => _sel('severity', v, sevValues,     sevLabel),
      },
    };
    const editable = editableSpecs[type] || {};
    const canSave  = !!(type === 'task' || type === 'issue');

    // 标题字段（显示在 toggle bar）
    const titleKey = cols.find(c => c.key === 'title' || c.key === 'name')?.key || 'title';
    if (titleEl) titleEl.textContent = item[titleKey] || '';

    // 其余字段逐行渲染
    const rowsHtml = cols
      .filter(c => c.key !== titleKey)
      .map(c => {
        const raw = item[c.key];
        const val = (raw !== undefined && raw !== null) ? String(raw) : '';
        const inner = editable[c.key]
          ? editable[c.key](val)
          : `<span class="wb-detail-field-val${!val ? ' is-empty' : ''}">${_esc(val || '—')}</span>`;
        return `<div class="wb-detail-field">
          <span class="wb-detail-field-label">${_esc(c.label)}</span>
          ${inner}
        </div>`;
      }).join('');

    body.innerHTML = `
      <div class="wb-detail-meta">
        <span class="wb-detail-badge">${typeLabels[type] || type}</span>
        ${canSave ? `<span class="wb-detail-save-msg" id="wb-detail-msg"></span>` : ''}
      </div>
      ${rowsHtml}
      <div class="wb-detail-save-row">
        <button class="wb-detail-open-btn" data-gid="${item.gid}" data-type="${type}">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          打开
        </button>
      </div>`;

    body.querySelector('.wb-detail-open-btn')?.addEventListener('click', () => {
      const tabMap = { task:'task', issue:'issue', bop_version:'bop',
                       pbom:'pbom', knowledge:'knowledge', rule:'rule' };
      _openTab(tabMap[type] || type);
    });

    if (canSave) {
      let _saveTimer = 0;
      const msgEl = body.querySelector('#wb-detail-msg');

      const _doSave = async (field, value) => {
        const fn = _cf(); if (!fn) return;
        if (msgEl) msgEl.textContent = '保存中…';
        try {
          const payload = { [field]: value || null };
          const endpoint = type === 'issue' ? `/api/issues/${item.gid}` : `/api/tasks/${item.gid}`;
          await fn(endpoint, { method:'PATCH', body: JSON.stringify(payload),
            headers: { 'Content-Type': 'application/json' } });
          Object.assign(item, payload);
          // 同步更新 _panelData[1] 中的原始条目，并刷新面板1分组
          if (_panelData[1]) {
            const orig = _panelData[1].find(r => r.gid === item.gid);
            if (orig) Object.assign(orig, payload);
            _renderPanelToday(_panelData[1]);
            if (_vis.cal) _renderCalendar();
            window.parent?.TaskTimeline?.refresh?.();
          }
          if (msgEl) { msgEl.textContent = '已保存'; setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 1500); }
        } catch { if (msgEl) msgEl.textContent = '保存失败'; }
      };

      body.querySelectorAll('.wb-detail-inp[data-field]').forEach(el => {
        el.addEventListener('change', () => {
          clearTimeout(_saveTimer);
          _saveTimer = setTimeout(() => _doSave(el.dataset.field, el.value.trim()), 300);
        });
      });
    }
  }

  // 收藏文件 右键 popover — 移入/移出文件夹
  function _showFavItemCtxMenu(e, gid, currentFolderId) {
    document.getElementById('_wbFavItemCtx')?.remove();
    const pop = document.createElement('div');
    pop.id = '_wbFavItemCtx';
    pop.className = 'wb-p2-ctx';
    let h = '';
    if (currentFolderId) {
      h += `<div class="wb-p2-ctx-action" data-action="unfolder">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2 4h4l1.5 2H14a1 1 0 011 1v6a1 1 0 01-1 1H2a1 1 0 01-1-1V5a1 1 0 011-1z"/><line x1="6" y1="11" x2="10" y2="11"/></svg>
        从文件夹移出
      </div>`;
    }
    const otherFolders = _favFolders.filter(f => f.id !== currentFolderId);
    if (otherFolders.length) {
      h += `<div class="wb-p2-ctx-lbl">移入文件夹</div>`;
      otherFolders.forEach(f => {
        h += `<div class="wb-p2-ctx-action" data-action="to-folder" data-folder-id="${_esc(f.id)}">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2 4h4l1.5 2H14a1 1 0 011 1v6a1 1 0 01-1 1H2a1 1 0 01-1-1V5a1 1 0 011-1z"/></svg>
          ${_esc(f.name)}
        </div>`;
      });
    }
    if (!h) h = `<div class="wb-p2-ctx-action wb-p2-ctx-muted">暂无文件夹可移入</div>`;
    pop.innerHTML = h;
    document.body.appendChild(pop);
    const x = Math.min(e.clientX, window.innerWidth - 180);
    const y = Math.min(e.clientY, window.innerHeight - pop.offsetHeight - 10);
    pop.style.cssText = `position:fixed;left:${x}px;top:${y}px;z-index:9999`;
    const remove = () => pop.remove();
    setTimeout(() => document.addEventListener('click', remove, { once: true }), 10);
    pop.addEventListener('click', e2 => {
      const action = e2.target.closest('[data-action]');
      if (!action) return;
      pop.remove();
      document.removeEventListener('click', remove);
      if (action.dataset.action === 'unfolder') {
        if (currentFolderId && _favFolderItems[currentFolderId]) {
          _favFolderItems[currentFolderId] = _favFolderItems[currentFolderId].filter(g => g !== gid);
          _saveFavFolders();
          _renderP2TreeSections(_treeSections);
        }
      } else if (action.dataset.action === 'to-folder') {
        const fid = action.dataset.folderId;
        if (currentFolderId && _favFolderItems[currentFolderId]) {
          _favFolderItems[currentFolderId] = _favFolderItems[currentFolderId].filter(g => g !== gid);
        }
        if (!_favFolderItems[fid]) _favFolderItems[fid] = [];
        if (!_favFolderItems[fid].includes(gid)) _favFolderItems[fid].push(gid);
        _saveFavFolders();
        _renderP2TreeSections(_treeSections);
      }
    });
  }

  // 文件树条目 通用右键菜单
  // 支持：清单(task/issue/knowledge/rule)、知识文档、BOP版本、PBOM版本
  function _showListItemCtxMenu(e, item) {
    document.getElementById('_wbListItemCtx')?.remove();
    const uid = window.top?._authUser?.gid || window.parent?._authUser?.gid || window._authUser?.gid || '';
    const fn  = window._cloudFetch || window.parent?._cloudFetch;

    // ── 类型分类 ──
    const isList    = ['task','issue','knowledge','rule'].includes(item.item_type);
    const isKhDoc   = ['knowledge_doc','site_page','weblink','feishu_doc','markdown','richtext','url','pdf'].includes(item.item_type);
    const isBopVer  = item.item_type === 'bop_version';
    const isPbom    = item.item_type === 'pbom';

    // ── owner 判断（各类型字段不同）──
    const ownerGid  = item.owner_gid || item.creator_gid || item.created_by || '';
    const isOwner   = !ownerGid || ownerGid === uid;

    // ── 打开文字 ──
    const openLabel = isKhDoc ? '打开文档' : isBopVer || isPbom ? '打开版本' : '在清单内打开';

    const pop = document.createElement('div');
    pop.id = '_wbListItemCtx';
    pop.className = 'wb-p2-ctx';

    let menuHtml = `
      <div class="wb-p2-ctx-action" data-action="open">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2" y="3" width="12" height="10" rx="1"/><line x1="5" y1="7" x2="11" y2="7"/><line x1="5" y1="10" x2="9" y2="10"/></svg>
        ${openLabel}
      </div>`;

    if (isOwner) {
      menuHtml += `<div class="wb-p2-ctx-sep"></div>
      <div class="wb-p2-ctx-action" data-action="rename">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 13h10M10 3l3 3-7 7H3V10z"/></svg>
        改名
      </div>`;

      // 可见范围 / 绑定项目 仅清单类型支持
      if (isList) {
        menuHtml += `
      <div class="wb-p2-ctx-action" data-action="visibility">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/></svg>
        设置可见范围 / 分享
      </div>
      <div class="wb-p2-ctx-action" data-action="project">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2" y="7" width="12" height="7" rx="1"/><path d="M5 7V5a3 3 0 016 0v2"/></svg>
        绑定项目
      </div>`;
      }
    }

    pop.innerHTML = menuHtml;
    document.body.appendChild(pop);

    const x = Math.min(e.clientX, window.innerWidth - 180);
    const y = Math.min(e.clientY, window.innerHeight - 180);
    pop.style.cssText = `position:fixed;left:${x}px;top:${y}px;z-index:9999`;

    const remove = () => pop.remove();
    setTimeout(() => document.addEventListener('click', remove, { once: true }), 10);

    pop.addEventListener('click', async e2 => {
      const action = e2.target.closest('[data-action]');
      if (!action) return;
      pop.remove();
      document.removeEventListener('click', remove);

      if (action.dataset.action === 'open') {
        _openListInP3(item);

      } else if (action.dataset.action === 'rename') {
        const curName = item.name || item.title || item.bop_name || '';
        const newName = await _promptText('改名', curName);
        if (!newName || newName === curName) return;

        try {
          if (isList) {
            await fn(`/api/lists/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ name: newName }) });
            item.name = newName;
          } else if (isKhDoc) {
            await fn(`/api/knowledge_hub/items/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ title: newName }) });
            item.title = newName; item.name = newName;
          } else if (isBopVer) {
            await fn(`/api/bop/versions/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ bop_name: newName }) });
            item.bop_name = newName; item.name = newName;
          } else if (isPbom) {
            await fn(`/api/ebom/snapshots/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ name: newName }) });
            item.name = newName;
          }
          _renderP2TreeSections(_treeSections);
        } catch (err) { alert('改名失败：' + (err.message || err)); }

      } else if (action.dataset.action === 'visibility') {
        _showListVisibilityDialog(item, fn);

      } else if (action.dataset.action === 'project') {
        _showListProjectDialog(item, fn);
      }
    });
  }

  // 可见范围设置对话框（仅清单类型）
  async function _showListVisibilityDialog(list, fn) {
    if (window.VisibilitySelector) {
      await VisibilitySelector.showDialog(list, async (val) => {
        await fn?.(`/api/lists/${list.gid}`, {
          method: 'PATCH',
          body: JSON.stringify({ visibility: val.visibility, shared_team_gid: val.shared_team_gid || null, project_gid: val.shared_project_gid || list.project_gid || null }),
        }).catch(err => alert('设置失败：' + err.message));
        list.visibility = val.visibility;
        list.shared_team_gid = val.shared_team_gid;
      });
      return;
    }
    // 降级
    document.getElementById('_wbListVisCtx')?.remove();
    const VIS_LABELS = { private: '仅自己', team: '团队', public: '公开', project: '项目内' };
    const cur = list.visibility || 'team';
    const dlg = document.createElement('div');
    dlg.id = '_wbListVisCtx';
    dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center';
    dlg.innerHTML = `
      <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px;width:320px;box-shadow:0 8px 32px rgba(0,0,0,.4)">
        <div style="font-size:14px;font-weight:600;color:var(--text-normal,#cdd6f4);margin-bottom:14px">设置可见范围 — ${_esc(list.name || '')}</div>
        <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:16px">
          ${['private','team','project','public'].map(v => `
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;padding:7px 10px;border-radius:6px;border:1px solid ${v===cur ? 'var(--color-accent,#89b4fa)' : 'var(--border-default,#313244)'}">
              <input type="radio" name="wb_vis" value="${v}" ${v===cur?'checked':''} style="accent-color:var(--color-accent,#89b4fa)">
              <span style="font-size:13px;color:var(--text-normal,#cdd6f4)">${VIS_LABELS[v]}</span>
            </label>`).join('')}
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <button id="_wbVisCancel" style="padding:5px 14px;border-radius:5px;border:1px solid var(--border-default,#313244);background:transparent;color:var(--text-muted,#a6adc8);cursor:pointer;font-size:12px">取消</button>
          <button id="_wbVisSave" style="padding:5px 14px;border-radius:5px;border:none;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);cursor:pointer;font-size:12px;font-weight:600">保存</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    dlg.querySelector('#_wbVisCancel').onclick = () => dlg.remove();
    dlg.querySelector('#_wbVisSave').onclick = async () => {
      const vis = dlg.querySelector('input[name="wb_vis"]:checked')?.value;
      if (!vis) { dlg.remove(); return; }
      await fn?.(`/api/lists/${list.gid}`, {
        method: 'PATCH', body: JSON.stringify({ visibility: vis }),
      }).catch(err => alert('设置失败：' + err.message));
      list.visibility = vis;
      dlg.remove();
    };
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.remove(); });
  }

  // 绑定项目对话框（仅清单类型）
  async function _showListProjectDialog(list, fn) {
    document.getElementById('_wbListProjCtx')?.remove();
    const projects = _allProjects?.length ? _allProjects
      : await fn?.('/api/projects').then(r => r?.data || r?.projects || []).catch(() => []) || [];

    const dlg = document.createElement('div');
    dlg.id = '_wbListProjCtx';
    dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center';
    dlg.innerHTML = `
      <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.4)">
        <div style="font-size:14px;font-weight:600;color:var(--text-normal,#cdd6f4);margin-bottom:14px">绑定项目 — ${_esc(list.name || '')}</div>
        <select id="_wbProjSel" style="width:100%;padding:7px 10px;background:var(--bg-primary,#1e1e2e);border:1px solid var(--border-default,#313244);border-radius:6px;color:var(--text-normal,#cdd6f4);font-size:13px;outline:none;margin-bottom:16px">
          <option value="">— 不关联项目 —</option>
          ${projects.map(p => `<option value="${_esc(p.gid)}" ${p.gid===list.project_gid?'selected':''}>${_esc(p.name||'')}</option>`).join('')}
        </select>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <button id="_wbProjCancel" style="padding:5px 14px;border-radius:5px;border:1px solid var(--border-default,#313244);background:transparent;color:var(--text-muted,#a6adc8);cursor:pointer;font-size:12px">取消</button>
          <button id="_wbProjSave" style="padding:5px 14px;border-radius:5px;border:none;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);cursor:pointer;font-size:12px;font-weight:600">保存</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    dlg.querySelector('#_wbProjCancel').onclick = () => dlg.remove();
    dlg.querySelector('#_wbProjSave').onclick = async () => {
      const projGid = dlg.querySelector('#_wbProjSel').value || null;
      await fn?.(`/api/lists/${list.gid}`, {
        method: 'PATCH', body: JSON.stringify({ project_gid: projGid }),
      }).catch(err => alert('绑定失败：' + err.message));
      list.project_gid = projGid;
      dlg.remove();
      _renderP2TreeSections(_treeSections);
    };
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.remove(); });
  }

  // 收藏文件夹 右键 popover — 重命名 / 删除
  function _showFavFolderCtxMenu(e, folderId) {
    document.getElementById('_wbFavFolderCtx')?.remove();
    const pop = document.createElement('div');
    pop.id = '_wbFavFolderCtx';
    pop.className = 'wb-p2-ctx';
    pop.innerHTML = `
      <div class="wb-p2-ctx-action" data-action="rename">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 13h10M10 3l3 3-7 7H3V10z"/></svg>
        重命名
      </div>
      <div class="wb-p2-ctx-action wb-p2-ctx-danger" data-action="delete">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="3,5 5,5 13,5"/><path d="M6 5V4a1 1 0 011-1h2a1 1 0 011 1v1"/><path d="M4 5l1 9a1 1 0 001 1h4a1 1 0 001-1l1-9"/></svg>
        删除文件夹
      </div>`;
    document.body.appendChild(pop);
    const x = Math.min(e.clientX, window.innerWidth - 160);
    const y = Math.min(e.clientY, window.innerHeight - 80);
    pop.style.cssText = `position:fixed;left:${x}px;top:${y}px;z-index:9999`;
    const remove = () => pop.remove();
    setTimeout(() => document.addEventListener('click', remove, { once: true }), 10);
    pop.addEventListener('click', async e2 => {
      const action = e2.target.closest('[data-action]');
      if (!action) return;
      pop.remove();
      document.removeEventListener('click', remove);
      if (action.dataset.action === 'rename') {
        const folder = _favFolders.find(f => f.id === folderId);
        if (!folder) return;
        const name = await _promptText('重命名文件夹', folder.name);
        if (!name) return;
        folder.name = name;
        _saveFavFolders();
        _renderP2TreeSections(_treeSections);
      } else if (action.dataset.action === 'delete') {
        _favFolders = _favFolders.filter(f => f.id !== folderId);
        delete _favFolderItems[folderId];
        _saveFavFolders();
        _renderP2TreeSections(_treeSections);
      }
    });
  }

  // 面板1行 右键 popover（详情 + 操作）
  function _showP1RowCtxMenu(e, item) {
    document.getElementById('_wbP1RowCtx')?.remove();
    const type = item.item_type || 'task';
    const canSave = type === 'task' || type === 'issue';

    // ── 可编辑字段 ──
    const _sel = (field, val, opts, labelMap) =>
      `<select class="wb-rctx-inp" data-field="${field}">${
        opts.map(o => `<option value="${o}"${o===val?' selected':''}>${labelMap[o]||o}</option>`).join('')
      }</select>`;
    const _date = (field, val) =>
      `<input class="wb-rctx-inp" type="date" data-field="${field}" value="${(val||'').substring(0,10)}">`;

    const taskStatuses  = ['pending','in_progress','done','cancelled'];
    const issueStatuses = ['open','in_progress','resolved','closed'];
    const statusLabel   = { pending:'待办', in_progress:'进行中', done:'完成', completed:'完成',
                            cancelled:'已取消', open:'待处理', resolved:'已解决', closed:'已关闭' };
    const prioValues    = ['urgent','high','medium','low'];
    const prioLabel     = { urgent:'紧急', high:'高', medium:'中', low:'低' };
    const sevValues     = ['critical','high','medium','low','info'];
    const sevLabel      = { critical:'严重', high:'高', medium:'中', low:'低', info:'提示' };

    const _time = (field, val) =>
      `<input class="wb-rctx-inp" type="time" data-field="${field}" value="${(val||'').substring(0,5)}">`;
    const _num  = (field, val, placeholder) =>
      `<input class="wb-rctx-inp" type="number" data-field="${field}" value="${val!=null?String(val):''}" min="0" step="5" placeholder="${placeholder||''}">`;
    const _numPresets = (field, val, presets) => {
      const cur = (val != null && val !== '') ? String(val) : '30';
      const btns = presets.map(p =>
        `<button type="button" class="wb-rctx-preset${String(p)===cur?' active':''}" data-rctx-preset="${field}" data-val="${p}">${p}</button>`
      ).join('');
      return `<div class="wb-rctx-num-group">${btns}<input class="wb-rctx-inp wb-rctx-num-inp" type="number" data-field="${field}" value="${cur}" min="1" step="5" placeholder="分"></div>`;
    };

    const editableSpecs = {
      task: {
        status:               (v) => _sel('status',               v, taskStatuses,  statusLabel),
        priority:             (v) => _sel('priority',             v, prioValues,    prioLabel),
        scheduled_date:       (v) => _date('scheduled_date',       v),
        scheduled_start_time: (v) => _time('scheduled_start_time', v),
        time_estimate:        (v) => _numPresets('time_estimate',  v, [15, 30, 60]),
        due_date:             (v) => _date('due_date',             v),
      },
      issue: {
        status:         (v) => _sel('status',         v, issueStatuses, statusLabel),
        severity:       (v) => _sel('severity',       v, sevValues,     sevLabel),
        scheduled_date: (v) => _date('scheduled_date', v),
      },
    };
    const editable = editableSpecs[type] || {};

    const fieldLabels = { status:'状态', priority:'优先级', scheduled_date:'计划日',
                          scheduled_start_time:'开始时刻', time_estimate:'时长(分钟)',
                          due_date:'截止日', severity:'严重度', project_name:'项目',
                          created_at:'创建时间' };
    const showFields = canSave
      ? Object.keys(editable)
      : ['status', 'priority', 'project_name'].filter(k => item[k] != null);

    const fieldsHtml = showFields.map(k => {
      const val = (item[k] !== undefined && item[k] !== null) ? String(item[k]) : '';
      const inner = editable[k]
        ? editable[k](val)
        : `<span class="wb-rctx-field-val">${_esc(val || '—')}</span>`;
      return `<div class="wb-rctx-field">
        <span class="wb-rctx-field-lbl">${fieldLabels[k] || k}</span>${inner}
      </div>`;
    }).join('');

    const pop = document.createElement('div');
    pop.id = '_wbP1RowCtx';
    pop.className = 'wb-row-ctx-pop';
    // 清单名：优先从缓存查找，其次 project_name
    const listName = (() => {
      if (item.list_gid && Array.isArray(_panel1ListsCache)) {
        const l = _panel1ListsCache.find(l => l.gid === item.list_gid);
        if (l) return l.name || l.title || '';
      }
      return item.project_name || '';
    })();
    const _fshAddSvg = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
    pop.innerHTML = `
      ${listName ? `<div class="wb-rctx-list">${_esc(listName)}</div>` : ''}
      <div class="wb-rctx-title">${_esc(item.title || item.name || '')}</div>
      ${canSave ? `<div class="wb-rctx-save-hint" id="_wbRCtxMsg"></div>` : ''}
      <div class="wb-rctx-fields">${fieldsHtml}</div>
      <div class="wb-rctx-feishu-section">
        <div class="wb-rctx-feishu-row">
          <span class="wb-rctx-fsh-lbl">飞书群</span>
          <div class="wb-rctx-fsh-chips" id="_wbRCtxGrpChips"><span class="wb-rctx-fsh-loading">…</span></div>
          ${canSave ? `<button class="wb-rctx-fsh-add" id="_wbRCtxAddGrp" title="添加群">${_fshAddSvg}</button>` : ''}
        </div>
        <div class="wb-rctx-feishu-row">
          <span class="wb-rctx-fsh-lbl">飞书文档</span>
          <div class="wb-rctx-fsh-chips" id="_wbRCtxDocChips"><span class="wb-rctx-fsh-loading">…</span></div>
          ${canSave ? `<button class="wb-rctx-fsh-add" id="_wbRCtxAddDoc" title="添加文档">${_fshAddSvg}</button>` : ''}
        </div>
      </div>
      <div class="wb-rctx-divider"></div>
      <div class="wb-rctx-action" id="_wbRCtxOpenList">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>
          <line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>
          <line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
        </svg>
        在清单内查看
      </div>
      <div class="wb-rctx-action" id="_wbRCtxViewLinks">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
        在查看器查看链接
      </div>`;

    document.body.appendChild(pop);

    // ── 飞书群/文档 区域 ──────────────────────────────────────────────
    {
      const _fopen = (url) => {
        const ea = window.electronAPI || window.parent?.electronAPI;
        if (ea?.openFeishuLink) ea.openFeishuLink(url);
        else if (ea?.shellOpenExternal) ea.shellOpenExternal(url);
        else window.open(url, '_blank');
      };
      let _grps = Array.isArray(item.feishu_groups) ? [...item.feishu_groups] : [];
      let _docs  = Array.isArray(item.feishu_docs)  ? [...item.feishu_docs]  : [];

      const _renderGrps = (arr) => {
        const el = pop.querySelector('#_wbRCtxGrpChips');
        if (!el) return;
        if (!arr.length) { el.innerHTML = '<span class="wb-rctx-fsh-empty">暂无</span>'; return; }
        el.innerHTML = arr.map((g, i) =>
          `<span class="wb-rctx-fsh-chip wb-rctx-fsh-grp" data-idx="${i}"># ${_esc(g.name || g.chat_id)}${canSave ? `<button class="wb-rctx-fsh-rm" data-rm-grp="${i}">×</button>` : ''}</span>`
        ).join('');
        el.querySelectorAll('.wb-rctx-fsh-grp').forEach((chip, i) => {
          chip.addEventListener('click', ev => {
            if (ev.target.closest('.wb-rctx-fsh-rm')) return;
            _fopen(`feishu://applink/client/chat/open?openChatId=${encodeURIComponent(arr[i].chat_id)}`);
          });
        });
      };
      const _renderDocs = (arr) => {
        const el = pop.querySelector('#_wbRCtxDocChips');
        if (!el) return;
        if (!arr.length) { el.innerHTML = '<span class="wb-rctx-fsh-empty">暂无</span>'; return; }
        el.innerHTML = arr.map((d, i) =>
          `<span class="wb-rctx-fsh-chip wb-rctx-fsh-doc" data-idx="${i}" title="${_esc(d.url || '')}">${_esc(d.title || d.url)}${canSave ? `<button class="wb-rctx-fsh-rm" data-rm-doc="${i}">×</button>` : ''}</span>`
        ).join('');
        el.querySelectorAll('.wb-rctx-fsh-doc').forEach((chip, i) => {
          chip.addEventListener('click', ev => {
            if (ev.target.closest('.wb-rctx-fsh-rm')) return;
            pop.remove();
            _openDocInViewer({ url: arr[i].url, title: arr[i].title || arr[i].url });
          });
        });
      };
      const _saveFsh = async (field, arr) => {
        const fn = _cf(); if (!fn) return;
        const ep = type === 'issue' ? `/api/issues/${item.gid}` : `/api/tasks/${item.gid}`;
        await fn(ep, { method: 'PATCH', body: JSON.stringify({ [field]: arr }),
          headers: { 'Content-Type': 'application/json' } }).catch(e => console.error('[fsh-save]', e));
        Object.assign(item, { [field]: arr });
      };

      // 懒加载完整数据（panel1 未返回 feishu_groups/feishu_docs）
      const fn = _cf();
      if (fn && item.gid) {
        const ep = type === 'issue' ? `/api/issues/${item.gid}` : `/api/tasks/${item.gid}`;
        fn(ep).then(res => {
          if (!pop.isConnected) return;
          if (res?.data) {
            _grps = Array.isArray(res.data.feishu_groups) ? [...res.data.feishu_groups] : _grps;
            _docs  = Array.isArray(res.data.feishu_docs)  ? [...res.data.feishu_docs]  : _docs;
          }
          _renderGrps(_grps); _renderDocs(_docs);
        }).catch(() => { _renderGrps(_grps); _renderDocs(_docs); });
      } else { _renderGrps(_grps); _renderDocs(_docs); }

      if (canSave) {
        // 删除群 chip
        pop.querySelector('#_wbRCtxGrpChips')?.addEventListener('click', async ev => {
          const rm = ev.target.closest('[data-rm-grp]'); if (!rm) return;
          _grps.splice(parseInt(rm.dataset.rmGrp), 1);
          await _saveFsh('feishu_groups', _grps); _renderGrps(_grps);
        });
        // 删除文档 chip
        pop.querySelector('#_wbRCtxDocChips')?.addEventListener('click', async ev => {
          const rm = ev.target.closest('[data-rm-doc]'); if (!rm) return;
          _docs.splice(parseInt(rm.dataset.rmDoc), 1);
          await _saveFsh('feishu_docs', _docs); _renderDocs(_docs);
        });
        // 添加群
        pop.querySelector('#_wbRCtxAddGrp')?.addEventListener('click', () => {
          if (!window.FeishuMentionChip) return;
          FeishuMentionChip.openPicker({
            mode: 'group',
            onSelect: async result => {
              if (!result.chat_id || _grps.find(g => g.chat_id === result.chat_id)) return;
              _grps.push({ chat_id: result.chat_id, name: result.name || result.chat_id });
              await _saveFsh('feishu_groups', _grps);
              pop.remove();
            },
          });
        });
        // 添加文档（搜索选择）
        pop.querySelector('#_wbRCtxAddDoc')?.addEventListener('click', () => {
          if (!window.FeishuMentionChip) return;
          FeishuMentionChip.openPicker({
            mode: 'doc',
            onSelect: async result => {
              if (!result.url || _docs.find(d => d.url === result.url)) return;
              _docs.push({ url: result.url, title: result.name || result.url });
              await _saveFsh('feishu_docs', _docs);
              pop.remove();
            },
          });
        });
      }
    }

    // 定位
    const pw = 270, ph = pop.offsetHeight || 300;
    let x = e.clientX, y = e.clientY;
    if (x + pw > window.innerWidth)  x = window.innerWidth  - pw - 6;
    if (y + ph > window.innerHeight) y = window.innerHeight - ph - 6;
    if (x < 4) x = 4;
    if (y < 4) y = 4;
    pop.style.left = x + 'px';
    pop.style.top  = y + 'px';

    // 自动保存（change 事件）
    if (canSave) {
      let _saveTimer = 0;
      const msgEl = pop.querySelector('#_wbRCtxMsg');
      const _doSave = async (field, value) => {
        const fn = _cf(); if (!fn) return;
        // 类型转换：INTEGER 列需要数字类型，否则 psycopg2 参数化查询类型不匹配
        let typedValue = value || null;
        if (field === 'time_estimate' && value) typedValue = parseInt(value, 10) || null;
        console.log('[p1-ctx-save] PATCH', field, '=', typedValue, 'gid=', item.gid);
        if (msgEl) msgEl.textContent = '保存中…';
        try {
          const payload = { [field]: typedValue };
          const endpoint = type === 'issue' ? `/api/issues/${item.gid}` : `/api/tasks/${item.gid}`;
          const res = await fn(endpoint, { method:'PATCH', body: JSON.stringify(payload),
            headers: { 'Content-Type': 'application/json' } });
          console.log('[p1-ctx-save] OK', field, res);
          Object.assign(item, payload);
          if (_panelData[1]) {
            const orig = _panelData[1].find(r => r.gid === item.gid);
            if (orig) Object.assign(orig, payload);
            _renderPanelToday(_panelData[1]);
            if (_vis.cal) _renderCalendar();
          }
          if (msgEl) { msgEl.textContent = '已保存'; setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 1500); }
        } catch(err) {
          console.error('[p1-ctx-save] FAILED', field, err);
          if (msgEl) msgEl.textContent = '保存失败';
        }
      };
      pop.querySelectorAll('.wb-rctx-inp[data-field]').forEach(el => {
        // 在事件触发时立即捕获值（不在 setTimeout 回调里读 el.value，
        // 避免 pop.remove() 后游离元素值被清空）
        const save = () => {
          const fieldName = el.dataset.field;
          const fieldVal  = el.value.trim();
          // 手动输入时同步预设按钮高亮
          if (el.type === 'number') {
            pop.querySelectorAll(`[data-rctx-preset="${fieldName}"]`).forEach(b =>
              b.classList.toggle('active', b.dataset.val === fieldVal));
          }
          console.log('[p1-ctx-save] input/change', fieldName, '=', fieldVal);
          clearTimeout(_saveTimer);
          _saveTimer = setTimeout(() => _doSave(fieldName, fieldVal), 300);
        };
        el.addEventListener('change', save);
        if (el.type === 'time' || el.type === 'number') el.addEventListener('input', save);
      });
      // 预设按钮：点击后更新 input 值并立即保存
      pop.querySelectorAll('[data-rctx-preset]').forEach(btn => {
        btn.addEventListener('click', () => {
          const field = btn.dataset.rctxPreset;
          const val   = btn.dataset.val;
          const inp   = pop.querySelector(`[data-field="${field}"]`);
          if (inp) inp.value = val;
          pop.querySelectorAll(`[data-rctx-preset="${field}"]`).forEach(b => b.classList.toggle('active', b === btn));
          clearTimeout(_saveTimer);
          _doSave(field, val);
        });
      });
    }

    // "在清单内查看"
    pop.querySelector('#_wbRCtxOpenList')?.addEventListener('click', () => {
      pop.remove();
      const tabType = type === 'issue' ? 'issue' : type === 'bop' ? 'bop' :
                      type === 'knowledge' ? 'knowledge' : type === 'rule' ? 'rule' : 'task';
      _openTab(tabType);
      // 切换到对应清单（ls:nav 由 main.js 中继到模块 iframe）
      if (item.list_gid) {
        window.parent?.postMessage({ type: 'ls:nav', itemType: tabType, gid: item.list_gid }, '*');
      }
      // 高亮并滚动到该条目（小延迟保证 ls:nav 先被模块处理）
      setTimeout(() => {
        window.parent?.postMessage({ type: 'ls:highlight', itemType: tabType, gid: item.gid }, '*');
      }, 50);
    });

    // "在查看器查看链接"
    pop.querySelector('#_wbRCtxViewLinks')?.addEventListener('click', () => {
      pop.remove();
      _loadItemLinks(item);
      // 切换中列到面板4（链接）
      if (!_vis.center) { _vis.center = true; _saveVis(); _switchCenterTab(4); _updateLayout(); }
      else { _switchCenterTab(4); }
      _focusPanel(3);
    });

    // 点外关闭（picker 打开时跳过，避免 picker 选择时误关闭 popup）
    setTimeout(() => document.addEventListener('mousedown', function close(ev) {
      if (document.getElementById('fm-picker-overlay')?.classList.contains('show')) return;
      if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener('mousedown', close); }
    }), 10);
  }

  // [3] 上下文详情（我的主业务，面板1无选中时的默认内容）
  function _renderPanelContext(contexts) {
    const body = document.getElementById('wb-body-3');
    if (!body) return;
    if (!contexts.length) {
      body.innerHTML = '<div class="wb-empty">尚未加入任何项目</div>';
      _setCount(3, 0, 0);
      return;
    }
    const filter = (_filterText[3] || '').toLowerCase();
    const filtered = filter
      ? contexts.filter(c =>
          (c.project_name || '').toLowerCase().includes(filter)
        )
      : contexts;

    const byProject = {};
    filtered.forEach(c => {
      if (!byProject[c.project_gid])
        byProject[c.project_gid] = { name: c.project_name, items: [] };
      byProject[c.project_gid].items.push(c);
    });

    const roleLabel = (r) => ({
      project_admin:'项目管理员', member:'成员', external:'外部',
      se_engineer:'SE工程师', team_admin:'团队管理员'
    }[r] || r || '成员');

    let html = '';
    let rowIdx = 0;
    Object.values(byProject).forEach(proj => {
      html += `<div class="wb-ctx-project">
        <div class="wb-ctx-proj-hdr">
          <span class="wb-ctx-proj-name">${_esc(proj.name)}</span>
        </div>`;
      proj.items.forEach(c => {
        html += `<div class="wb-row wb-ctx-scope"
                      data-idx="${rowIdx}"
                      data-project-gid="${c.project_gid}"
                      data-section-gid="${c.section_gid || ''}">
          <span class="wb-row-type ctx"></span>
          <span class="wb-ctx-role">${_esc(roleLabel(c.role))}</span>
          <span class="wb-ctx-scope-name">${_esc(c.section_gid || '项目级')}</span>
          <button class="wb-ctx-enter" data-project-gid="${c.project_gid}">进画布 →</button>
        </div>`;
        rowIdx++;
      });
      html += '</div>';
    });
    body.innerHTML = html;

    body.querySelectorAll('.wb-ctx-enter').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        _openTab('canvas', { project_gid: btn.dataset.projectGid });
      });
    });
    body.querySelectorAll('.wb-row').forEach((row, i) => {
      row.addEventListener('click', () => _selectRow(3, i));
      row.addEventListener('dblclick', () => {
        _openTab('canvas', { project_gid: row.dataset.projectGid });
      });
    });
    _setCount(3, rowIdx, contexts.length);
  }

  // [4] 我关注的
  function _renderPanelFollows(follows) {
    const body = document.getElementById('wb-body-4');
    if (!body) return;
    if (!follows.length) {
      body.innerHTML = '<div class="wb-empty">暂无关注条目</div>';
      _setCount(4, 0, 0);
      return;
    }
    const typeLabel = (t) =>
      ({ task:'任务', issue:'问题', knowledge:'知识', rule:'规则' }[t] || t);

    body.innerHTML = follows.map((item, i) => `
      <div class="wb-row" data-idx="${i}" data-gid="${item.item_gid}" data-type="${item.item_type}">
        <span class="wb-row-type follow"></span>
        <span class="wb-row-title" title="${_esc(item.item_title)}">${_esc(item.item_title)}</span>
        <span class="wb-row-badge">${typeLabel(item.item_type)}</span>
      </div>
    `).join('');

    body.querySelectorAll('.wb-row').forEach((row, i) => {
      row.addEventListener('click', () => { _selectRow(4, i); _openTab(row.dataset.type); });
    });
    _setCount(4, follows.length, follows.length);
  }

  // [5] 变更预警（占位）
  function _renderPanelAlerts(alerts) {
    const body = document.getElementById('wb-body-5');
    if (!body) return;
    body.innerHTML = alerts.length
      ? alerts.map(a => `<div class="wb-row"><span class="wb-row-title">${_esc(a.title || a)}</span></div>`).join('')
      : '<div class="wb-empty">暂无变更预警</div>';
    _setCount(5, alerts.length, alerts.length);
  }

  // [6] 项目状态（占位）
  function _renderPanelStatus(items) {
    const body = document.getElementById('wb-body-6');
    if (!body) return;
    if (!items.length) {
      body.innerHTML = '<div class="wb-empty">暂无项目状态数据</div>';
      _setCount(6, 0, 0);
      return;
    }
    body.innerHTML = items.map(it => `
      <div class="wb-row">
        <span class="wb-row-type ctx"></span>
        <span class="wb-row-title">${_esc(it.project_name || it.name)}</span>
      </div>
    `).join('');
    _setCount(6, items.length, items.length);
  }

  // ── 条目链接 [4] ──────────────────────────────────────────────────────────
  function _loadItemLinks(item) {
    _links = [];
    // 从 description / content_ref 等字段提取 URL
    const text = [item.description, item.content_ref, item.notes].filter(Boolean).join(' ');
    const urlRe = /https?:\/\/[^\s"'<>]+/g;
    const found = text.match(urlRe) || [];
    found.forEach(url => {
      if (!_links.find(l => l.url === url)) {
        _links.push({ url, title: _urlTitle(url) });
      }
    });
    _linkIdx = 0;
    _renderLinkTabs();
  }

  function _urlTitle(url) {
    try {
      const u = new URL(url);
      if (u.hostname.includes('feishu.cn') || u.hostname.includes('larksuite.com'))
        return '飞书文档';
      return u.hostname.replace('www.', '');
    } catch { return url.substring(0, 30); }
  }

  function _renderLinkTabs() {
    const tabsEl  = document.getElementById('wbLinkTabs');
    const viewer  = document.getElementById('wbLinkViewer');
    if (!tabsEl || !viewer) return;

    if (!_links.length) {
      tabsEl.innerHTML = '';
      viewer.innerHTML = '<div class="wb-empty">当前条目没有外部链接</div>';
      return;
    }

    tabsEl.innerHTML = _links.map((l, i) =>
      `<button class="wb-link-tab${i === _linkIdx ? ' active' : ''}" data-idx="${i}">${_esc(l.title)}</button>`
    ).join('');
    tabsEl.querySelectorAll('.wb-link-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        _linkIdx = +btn.dataset.idx;
        _renderLinkTabs();
      });
    });
    _showLink(_links[_linkIdx]);
  }

  function _showLink(link) {
    const viewer = document.getElementById('wbLinkViewer');
    if (!viewer) return;
    viewer.innerHTML = `
      <iframe src="${_esc(link.url)}" title="${_esc(link.title)}"
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        onerror="this.style.display='none'"
        onload="if(this.contentDocument && this.contentDocument.body.innerHTML === '') { this.style.display='none'; }"
      ></iframe>
      <div class="wb-link-external" id="wbLinkExternal" style="display:none">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".3">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
          <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
        <span class="wb-link-ext-url">${_esc(link.url)}</span>
        <button class="wb-link-ext-btn" onclick="window.open('${_esc(link.url)}','_blank')">在浏览器中打开</button>
      </div>
    `;
    // iframe 加载失败时显示外部链接按钮
    const iframe = viewer.querySelector('iframe');
    if (iframe) {
      iframe.addEventListener('error', () => {
        iframe.style.display = 'none';
        const ext = document.getElementById('wbLinkExternal');
        if (ext) ext.style.display = 'flex';
      });
    }
  }

  function _cycleLinkTab(delta) {
    if (!_links.length) return;
    _linkIdx = (_linkIdx + delta + _links.length) % _links.length;
    _renderLinkTabs();
  }

  // ── 小日历 ───────────────────────────────────────────────────────────────
  function _renderCalendar() {
    const body = document.getElementById('wbCalBody');
    if (!body) return;

    const year  = _calYear;
    const month = _calMonth;
    const todayD = new Date();
    const todayStr = `${todayD.getFullYear()}-${String(todayD.getMonth()+1).padStart(2,'0')}-${String(todayD.getDate()).padStart(2,'0')}`;

    // 收集有事件的日期
    const eventDays = {};
    (_panelData[1] || []).forEach(item => {
      const d = item.due_date || item.scheduled_date;
      if (d) {
        const key = String(d).substring(0, 10);
        if (!eventDays[key]) eventDays[key] = [];
        eventDays[key].push(item);
      }
    });

    const firstWeekday = new Date(year, month, 1).getDay();  // 0=Sun
    const daysInMonth  = new Date(year, month + 1, 0).getDate();
    const monthNames   = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
    const dowNames     = ['日','一','二','三','四','五','六'];

    let html = `
      <div class="wb-cal-nav">
        <button class="wb-cal-nav-btn" id="wbCalPrev">‹</button>
        <span class="wb-cal-month">${year}年${monthNames[month]}</span>
        <button class="wb-cal-nav-btn" id="wbCalNext">›</button>
      </div>
      <div class="wb-cal-grid">
        ${dowNames.map(d => `<div class="wb-cal-dow">${d}</div>`).join('')}
        ${Array(firstWeekday).fill('<div class="wb-cal-day wb-cal-empty"></div>').join('')}
    `;

    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const isToday = dateStr === todayStr;
      const hasEv   = !!eventDays[dateStr];
      html += `<div class="wb-cal-day${isToday ? ' wb-cal-today' : ''}${hasEv ? ' wb-cal-has-event' : ''}"
                    data-date="${dateStr}">
        <span>${d}</span>
        ${hasEv ? '<span class="wb-cal-dot"></span>' : ''}
      </div>`;
    }

    html += `</div>`;

    // 项目健康度
    const ctxData = _panelData[3] || [];
    if (ctxData.length) {
      html += `<div class="wb-cal-projects">
        <div class="wb-cal-proj-hdr">项目健康度</div>
        ${[...new Map(ctxData.map(c => [c.project_gid, c])).values()].map(c => `
          <div class="wb-cal-proj-row">
            <span class="wb-cal-health green"></span>
            <span class="wb-cal-proj-name">${_esc(c.project_name)}</span>
          </div>
        `).join('')}
      </div>`;
    }

    // 面板1计划条目：selected day 精确匹配 + 有开始时刻 + 有时长 + 未完成
    _refilterCalPlanItems(_calSelectedDay);

    // 统一时间线区域（计划条目立即渲染，飞书日程异步注入）
    const isToday = (_calSelectedDay === todayStr);
    const tlHdr = isToday ? '今日时间线' : `${_calSelectedDay} 时间线`;
    html += `<div class="wb-cal-timeline-wrap" id="wbCalTimeline">
      <div class="wb-cal-tl-hdr">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="margin-right:4px;vertical-align:-1px">
          <circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4"/>
          <path d="M8 4v4l2.5 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
        ${tlHdr}
      </div>
      <div class="wb-cal-tl-body" id="wbCalTlBody">
        ${_buildUnifiedTimelineHTML(_calPlanItems, null)}
      </div>
    </div>`;

    body.innerHTML = html;

    // 异步加载飞书日程（不阻塞日历渲染）
    _loadFeishuAgenda();
    // 初始滚动到当前时刻
    setTimeout(_dvScrollToNow, 50);
    // 绑定拖拽/右键交互
    setTimeout(() => _initDvInteractions(document.getElementById('wbCalTlBody')), 60);

    // 事件绑定
    document.getElementById('wbCalPrev')?.addEventListener('click', () => {
      _calMonth--;
      if (_calMonth < 0) { _calMonth = 11; _calYear--; }
      _renderCalendar();
    });
    document.getElementById('wbCalNext')?.addEventListener('click', () => {
      _calMonth++;
      if (_calMonth > 11) { _calMonth = 0; _calYear++; }
      _renderCalendar();
    });
    body.querySelectorAll('.wb-cal-day[data-date]').forEach(el => {
      el.addEventListener('click', (e) => {
        const clickedDate = el.dataset.date;
        const evs = eventDays[clickedDate];
        // 更新选中日并刷新时间线
        _calSelectedDay = clickedDate;
        _calFeishuItems = null; // 清除缓存，触发重新加载
        _refilterCalPlanItems(_calSelectedDay);
        // 更新时间线标题
        const tlHdrEl = document.querySelector('#wbCalTimeline .wb-cal-tl-hdr');
        if (tlHdrEl) {
          const isToday = (_calSelectedDay === _wbTodayStr());
          tlHdrEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="margin-right:4px;vertical-align:-1px">
            <circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4"/>
            <path d="M8 4v4l2.5 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          </svg>${isToday ? '今日时间线' : `${_calSelectedDay} 时间线`}`;
        }
        // 先渲染计划条目，再异步加载飞书日程
        const tlBody = document.getElementById('wbCalTlBody');
        if (tlBody) {
          tlBody.innerHTML = _buildUnifiedTimelineHTML(_calPlanItems, null);
          _initDvInteractions(tlBody);
        }
        _loadFeishuAgenda(_calSelectedDay);
        // 日期格子 popover
        _showCalPopover(el, clickedDate, evs || []);
      });
    });
  }

  function _showCalPopover(anchor, dateStr, events) {
    const pop  = document.getElementById('wbCalPopover');
    const date = document.getElementById('wbCalPopDate');
    const popBody = document.getElementById('wbCalPopBody');
    if (!pop || !date || !popBody) return;

    date.textContent = dateStr;
    popBody.innerHTML = events.length
      ? events.map(e => `
          <div class="wb-cal-pop-item">
            <span class="wb-row-type ${e.item_type === 'issue' ? 'issue' : 'task'}"></span>
            <span>${_esc(e.title)}</span>
          </div>`).join('')
      : '<div style="font-size:11px;color:var(--text-faint)">无事件</div>';

    // 定位 popover
    const rect = anchor.getBoundingClientRect();
    pop.classList.remove('hidden');
    const pw = pop.offsetWidth || 220;
    const ph = pop.offsetHeight || 140;
    let left = rect.left;
    let top  = rect.bottom + 4;
    if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8;
    if (top  + ph > window.innerHeight - 30) top = rect.top - ph - 4;
    pop.style.left = left + 'px';
    pop.style.top  = top  + 'px';

    const close = () => { pop.classList.add('hidden'); document.removeEventListener('click', onOutside, true); };
    const onOutside = (e) => { if (!pop.contains(e.target) && !anchor.contains(e.target)) close(); };
    setTimeout(() => document.addEventListener('click', onOutside, true), 10);
    document.getElementById('wbCalPopClose')?.addEventListener('click', close, { once: true });
  }

  // ── 忽略日程（localStorage 持久化） ──────────────────────────────────────
  const _LS_IGN = 'wb:cal-ignored';
  const _ignoredEvts = new Set(JSON.parse(localStorage.getItem(_lsk(_LS_IGN)) || '[]'));
  function _saveIgnored() { localStorage.setItem(_lsk(_LS_IGN), JSON.stringify([..._ignoredEvts])); }

  function _renderAgendaItem(ev, rsvpLabel, rsvpClass) {
    return `<div class="wb-cal-agenda-item" data-event-id="${_esc(ev.event_id || '')}"
         data-is-organizer="${ev.is_organizer ? '1' : '0'}"
         data-rsvp="${_esc(ev.rsvp || 'needs_action')}"
         data-summary="${_esc(ev.summary || '')}"
         data-description="${_esc(ev.description || '')}">
      <div class="wb-cal-agenda-time">${_esc(ev.start)} – ${_esc(ev.end)}</div>
      <div class="wb-cal-agenda-row">
        <span class="wb-cal-agenda-rsvp ${rsvpClass[ev.rsvp] || 'pending'}">${rsvpLabel[ev.rsvp] || '?'}</span>
        <span class="wb-cal-agenda-title">${_esc(ev.summary)}</span>
        ${ev.meeting_url ? `<a class="wb-cal-agenda-vc" href="${_esc(ev.meeting_url)}" target="_blank" title="加入会议">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
            <rect x="1" y="4" width="10" height="8" rx="1" stroke="currentColor" stroke-width="1.4"/>
            <path d="M11 7l4-3v8l-4-3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
          </svg>
        </a>` : ''}
      </div>
    </div>`;
  }

  // ── 日历 Day-View 渲染 ────────────────────────────────────────────────────
  const _DV_START = 8 * 60;   // 08:00 → 480 min
  const _DV_END   = 22 * 60;  // 22:00 → 1320 min
  const _DV_SLOT  = 26;       // px per 30-min slot

  function _tToMin(t) {
    if (!t) return null;
    const [h, m] = String(t).substring(0, 5).split(':').map(Number);
    return isNaN(h) || isNaN(m) ? null : h * 60 + m;
  }

  /**
   * 构建 Day-View HTML。
   * planItems  — 来自面板1的计划条目（已过滤）
   * feishuItems — 飞书日程数组，null 表示加载中
   */
  function _buildUnifiedTimelineHTML(planItems, feishuItems) {
    const totalSlots = (_DV_END - _DV_START) / 30;   // 28
    const totalH     = totalSlots * _DV_SLOT;         // 728 px

    const now    = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const nowY   = (nowMin - _DV_START) / _DV_SLOT * _DV_SLOT;  // reuse scale
    const toY    = (m) => (m - _DV_START) / 30 * _DV_SLOT;
    const nowVis = nowMin >= _DV_START && nowMin <= _DV_END;

    const td = now;
    const todayStr = `${td.getFullYear()}-${String(td.getMonth()+1).padStart(2,'0')}-${String(td.getDate()).padStart(2,'0')}`;

    // ── collect events ──────────────────────────────────────────────────────
    const evs = [];
    planItems.forEach(it => {
      const sMin = _tToMin(it.scheduled_start_time);
      if (sMin === null) return;
      const dur = it.time_estimate ? Number(it.time_estimate) : 30;
      evs.push({
        _k: 'plan', sMin, eMin: sMin + dur,
        gid: it.gid, itemType: it.item_type || 'task',
        title: it.title || '',
        isOverdue: it.scheduled_date && String(it.scheduled_date).substring(0, 10) < todayStr,
      });
    });
    if (feishuItems) {
      const rsvpCls = { accept:'accept', decline:'decline', needs_action:'pending', tentative:'tentative' };
      const rsvpLbl = { accept:'✓', decline:'✗', needs_action:'?', tentative:'~' };
      feishuItems.forEach(ev => {
        const sMin = _tToMin(ev.start), eMin = _tToMin(ev.end);
        if (sMin === null || eMin === null) return;
        const isIgnored = _ignoredEvts.has(ev.event_id);
        const isDeclined = ev.rsvp === 'decline';
        evs.push({
          _k:'feishu', sMin, eMin,
          title: ev.summary || '', rsvp: ev.rsvp, rsvpLbl, rsvpCls,
          meeting_url: ev.meeting_url, event_id: ev.event_id,
          is_organizer: ev.is_organizer, summary: ev.summary, description: ev.description,
          _dim: isIgnored || isDeclined,
        });
      });
    }

    // ── greedy column assignment ─────────────────────────────────────────────
    // 先按开始时间排序，dim（拒绝/忽略）事件在同时刻排在后面 → 自然分配到最右侧列
    evs.sort((a, b) => a.sMin - b.sMin || (a._dim ? 1 : 0) - (b._dim ? 1 : 0));
    const colEnds = [];
    evs.forEach(ev => {
      let c = colEnds.findIndex(e => e <= ev.sMin);
      if (c < 0) c = colEnds.length;
      colEnds[c] = ev.eMin;
      ev._col = c;
    });
    const numCols = Math.max(1, colEnds.length);
    const CW = 100 / numCols;

    // ── hour labels ──────────────────────────────────────────────────────────
    let labelsH = '';
    for (let t = _DV_START; t <= _DV_END; t += 60) {
      const y = toY(t);
      labelsH += `<div class="wb-dv-lbl" style="top:${y}px">${String(Math.floor(t/60)).padStart(2,'0')}:00</div>`;
    }

    // ── slot grid lines ──────────────────────────────────────────────────────
    let slotsH = '';
    for (let i = 0; i < totalSlots; i++) {
      slotsH += `<div class="wb-dv-slot${i % 2 === 0 ? ' wb-dv-slot-hr' : ''}"></div>`;
    }

    // ── event blocks ─────────────────────────────────────────────────────────
    const _domLbl = { task:'T', issue:'I', bop:'B', knowledge:'K', rule:'R' };
    let evH = '';
    evs.forEach(ev => {
      const cs = Math.max(ev.sMin, _DV_START);
      const ce = Math.min(ev.eMin, _DV_END);
      if (ce <= cs) return;
      const top = toY(cs);
      const h   = Math.max(toY(ce) - top, 18);
      const L   = ev._col * CW;
      if (ev._k === 'plan') {
        const type = ev.itemType;
        const dl   = _domLbl[type] || type[0].toUpperCase();
        evH += `<div class="wb-dv-ev wb-dv-ev-plan${ev.isOverdue ? ' wb-dv-ev-over' : ''}"
          title="${_esc(ev.title)}"
          data-gid="${_esc(ev.gid||'')}" data-item-type="${ev.itemType}"
          style="top:${top}px;height:${h}px;left:calc(${L}% + 1px);width:calc(${CW}% - 3px)">
          <span class="wb-row-domain-tag type-${type}" style="font-size:9px;padding:0 3px;line-height:14px">${dl}</span>
          <span class="wb-dv-ev-ttl">${_esc(ev.title)}</span>
          <div class="wb-dv-ev-resize"></div>
        </div>`;
      } else {
        const rc = (ev.rsvpCls||{})[ev.rsvp] || 'pending';
        const rl = (ev.rsvpLbl||{})[ev.rsvp] || '?';
        const rsvpBg = ev._dim
          ? 'rgba(127,127,127,0.4)'
          : ({ accept:'#a6e3a1', decline:'#f38ba8', pending:'#f9e2af', tentative:'#89b4fa44' }[rc] || '#f9e2af');
        const dimStyle = ev._dim ? 'opacity:0.45;filter:grayscale(1);' : '';
        evH += `<div class="wb-dv-ev wb-dv-ev-feishu${ev._dim ? ' wb-dv-ev-dim' : ''}"
          title="${_esc(ev.title)}"
          data-event-id="${_esc(ev.event_id||'')}" data-is-organizer="${ev.is_organizer?'1':'0'}"
          data-rsvp="${_esc(ev.rsvp||'needs_action')}" data-summary="${_esc(ev.summary||'')}"
          data-description="${_esc(ev.description||'')}" data-meeting-url="${_esc(ev.meeting_url||'')}"
          style="top:${top}px;height:${h}px;left:calc(${L}% + 1px);width:calc(${CW}% - 3px);${dimStyle}">
          <span class="wb-dv-feishu-badge" style="background:${rsvpBg}">${rl}</span>
          <span class="wb-dv-ev-ttl">${_esc(ev.title)}</span>
        </div>`;
      }
    });

    // ── now-line ─────────────────────────────────────────────────────────────
    const nowLine = nowVis
      ? `<div class="wb-dv-now" style="top:${toY(nowMin)}px"></div>` : '';

    // ── loading hint ──────────────────────────────────────────────────────────
    const loadingHint = feishuItems === null
      ? `<div class="wb-dv-loading">飞书日程加载中…</div>` : '';

    return `<div class="wb-dv-wrap" id="wbDvScroll">
      <div class="wb-dv-inner">
        <div class="wb-dv-labels" style="height:${totalH}px">${labelsH}</div>
        <div class="wb-dv-col" style="height:${totalH}px">${slotsH}${evH}${nowLine}${loadingHint}</div>
      </div>
    </div>`;
  }

  async function _loadFeishuAgenda(date) {
    const tlBody = document.getElementById('wbCalTlBody');
    if (!tlBody) return;
    // 若面板1设置中未勾选飞书日历，清空飞书条目并跳过 API
    if (!(_p1Settings.sources || []).includes('feishu')) {
      _calFeishuItems = [];
      tlBody.innerHTML = _buildUnifiedTimelineHTML(_calPlanItems, []);
      _dvScrollToNow();
      _initDvInteractions(tlBody);
      tlBody.removeEventListener('contextmenu', _onAgendaContextMenu);
      return;
    }
    const targetDate = date || _calSelectedDay;
    try {
      const url = `/feishu/calendar/today${targetDate ? `?date=${targetDate}` : ''}`;
      const res = await (window._cloudFetch || window.parent?._cloudFetch)(url);
      const feishuData = (res.success && res.data?.length) ? res.data : [];
      _calFeishuItems = feishuData;
      tlBody.innerHTML = _buildUnifiedTimelineHTML(_calPlanItems, feishuData);
      _dvScrollToNow();
      _initDvInteractions(tlBody);
      // 右键菜单（飞书条目）
      tlBody.removeEventListener('contextmenu', _onAgendaContextMenu);
      tlBody.addEventListener('contextmenu', _onAgendaContextMenu);
    } catch (e) {
      tlBody.innerHTML = _buildUnifiedTimelineHTML(_calPlanItems, []);
    }
  }

  /** 重新过滤计划条目（targetDate 为 'YYYY-MM-DD'，默认当天） */
  function _refilterCalPlanItems(targetDate) {
    if (!targetDate) targetDate = _wbTodayStr();
    const doneSts = new Set(['done', 'completed', 'cancelled']);
    _calPlanItems = (_panelData[1] || [])
      .filter(it => {
        const d = it.scheduled_date ? String(it.scheduled_date).substring(0, 10) : null;
        return d && d === targetDate && it.scheduled_start_time && !doneSts.has(it.status);
      })
      .slice()
      .sort((a, b) => String(a.scheduled_start_time).localeCompare(String(b.scheduled_start_time)));
  }

  /** 用缓存数据重新渲染 day-view（不重新请求飞书） */
  function _refreshDayView() {
    const tlBody = document.getElementById('wbCalTlBody');
    if (!tlBody) return;
    tlBody.innerHTML = _buildUnifiedTimelineHTML(_calPlanItems, _calFeishuItems || []);
    _initDvInteractions(tlBody);
  }

  /** PATCH 一个条目字段到 DB，并同步更新 panel1 缓存 */
  async function _dvPatchItem(gid, itemType, fields) {
    const cf = _cf();
    if (!cf) throw new Error('cloudFetch 不可用，请检查登录状态');
    const endpoint = itemType === 'task' ? `/api/tasks/${gid}` : `/api/issues/${gid}`;
    await cf(endpoint, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    });
    // 同步更新内存
    const arr = _panelData[1] || [];
    const idx = arr.findIndex(it => it.gid === gid);
    if (idx >= 0) Object.assign(arr[idx], fields);
    // 刷新 panel1 行和 day-view
    _renderPanelToday(_panelData[1] || []);
    _refilterCalPlanItems(_calSelectedDay);
    _refreshDayView();
    // 同步刷新状态栏日程（workbench 在 iframe 里，TaskTimeline 在 parent frame）
    window.parent?.TaskTimeline?.refresh?.();
  }

  /** 分钟数 → "HH:MM" 字符串 */
  function _minToTimeStr(m) {
    const h = Math.floor(m / 60);
    const mm = m % 60;
    return `${String(h).padStart(2,'0')}:${String(mm).padStart(2,'0')}`;
  }

  /** 初始化 day-view 拖拽/右键交互 */
  function _initDvInteractions(container) {
    if (!container) return;
    container.querySelectorAll('.wb-dv-ev-plan').forEach(evEl => {
      // 右键菜单：与 Panel1 共用
      evEl.addEventListener('contextmenu', e => {
        e.preventDefault();
        e.stopPropagation();
        const gid = evEl.dataset.gid;
        const itemType = evEl.dataset.itemType;
        if (!gid) return;
        const arr = _panelData[1] || [];
        const item = arr.find(it => it.gid === gid);
        if (item) _showP1RowCtxMenu(e, item);
      });

      // 拖拽移动（整个事件块）
      evEl.addEventListener('mousedown', e => {
        if (e.target.classList.contains('wb-dv-ev-resize')) return; // 交给 resize
        if (e.button !== 0) return;
        e.preventDefault();
        _dvStartDrag(e, evEl);
      });

      // 拖拽调整大小（底部 resize handle）
      const resizeHandle = evEl.querySelector('.wb-dv-ev-resize');
      if (resizeHandle) {
        resizeHandle.addEventListener('mousedown', e => {
          if (e.button !== 0) return;
          e.preventDefault();
          e.stopPropagation();
          _dvStartResize(e, evEl);
        });
      }
    });
  }

  /** 拖拽移动：改变 scheduled_start_time */
  function _dvStartDrag(e, evEl) {
    const col = evEl.closest('.wb-dv-col');
    if (!col) return;
    const colRect = col.getBoundingClientRect();
    const startY = e.clientY;
    const origTop = parseInt(evEl.style.top) || 0;
    evEl.classList.add('wb-dv-ev-dragging');

    const onMove = mv => {
      const deltaY = mv.clientY - startY;
      const deltaMin = deltaY / _DV_SLOT * 30;
      const snapped = Math.round(deltaMin / 5) * 5;
      const newTop = Math.max(0, origTop + snapped / 30 * _DV_SLOT);
      evEl.style.top = newTop + 'px';
    };

    const onUp = async () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      evEl.classList.remove('wb-dv-ev-dragging');

      const newTop = parseInt(evEl.style.top) || 0;
      const newMin = Math.round(newTop / _DV_SLOT * 30 / 5) * 5 + _DV_START;
      const clamped = Math.max(_DV_START, Math.min(_DV_END - 30, newMin));
      const newTime = _minToTimeStr(clamped);

      const gid = evEl.dataset.gid;
      const itemType = evEl.dataset.itemType;
      if (!gid) return;
      try {
        await _dvPatchItem(gid, itemType, { scheduled_start_time: newTime + ':00' });
      } catch (err) {
        console.error('dv drag patch failed', err);
        _showWbToast('保存失败：' + (err?.message || '网络错误'), 'error');
        _refreshDayView(); // 回滚到保存前状态
      }
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  /** 拖拽调整大小：改变 time_estimate */
  function _dvStartResize(e, evEl) {
    const startY = e.clientY;
    const origH = parseInt(evEl.style.height) || _DV_SLOT;
    evEl.classList.add('wb-dv-ev-resizing');

    const onMove = mv => {
      const deltaY = mv.clientY - startY;
      const deltaMin = deltaY / _DV_SLOT * 30;
      const snapped = Math.round(deltaMin / 5) * 5;
      const newH = Math.max(_DV_SLOT, origH + snapped / 30 * _DV_SLOT);
      evEl.style.height = newH + 'px';
    };

    const onUp = async () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      evEl.classList.remove('wb-dv-ev-resizing');

      const newH = parseInt(evEl.style.height) || _DV_SLOT;
      const newMin = Math.round(newH / _DV_SLOT * 30 / 5) * 5;
      const clamped = Math.max(5, newMin);

      const gid = evEl.dataset.gid;
      const itemType = evEl.dataset.itemType;
      if (!gid) return;
      try {
        await _dvPatchItem(gid, itemType, { time_estimate: clamped });
      } catch (err) {
        console.error('dv resize patch failed', err);
        _showWbToast('保存失败：' + (err?.message || '网络错误'), 'error');
        _refreshDayView(); // 回滚到保存前状态
      }
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  /** 滚动 day-view 到当前时刻附近 */
  function _dvScrollToNow() {
    const wrap = document.getElementById('wbDvScroll');
    if (!wrap) return;
    const now    = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    if (nowMin < _DV_START || nowMin > _DV_END) return;
    const nowY     = (nowMin - _DV_START) / 30 * _DV_SLOT;
    wrap.scrollTop = Math.max(0, nowY - wrap.offsetHeight * 0.35);
  }

  /** 每分钟更新红线位置 */
  setInterval(() => {
    const line = document.querySelector('.wb-dv-now');
    if (!line) return;
    const now    = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    if (nowMin >= _DV_START && nowMin <= _DV_END) {
      line.style.top = `${(nowMin - _DV_START) / 30 * _DV_SLOT}px`;
    }
  }, 60000);

  /** 每 5 分钟自动刷新飞书日历数据（_calFeishuItems 清空后下次渲染时重新拉取）*/
  setInterval(() => {
    if (!_vis.cal) return;           // 面板未展开则跳过
    _calFeishuItems = null;          // 清除缓存
    _refilterCalPlanItems(_calSelectedDay);
    const tlBody = document.getElementById('wbCalTlBody');
    if (tlBody) {
      // 触发实际拉取（同 日期点击 逻辑）
      const fn = window._cloudFetch || window.parent?._cloudFetch;
      if (!fn) return;
      const date = _calSelectedDay;
      fn(`/feishu/calendar/today${date ? `?date=${date}` : ''}`)
        .then(res => {
          _calFeishuItems = (res?.success && res.data?.length) ? res.data : [];
          if (document.getElementById('wbCalTlBody')) {
            document.getElementById('wbCalTlBody').innerHTML =
              _buildUnifiedTimelineHTML(_calPlanItems, _calFeishuItems);
            _dvScrollToNow();
            _initDvInteractions(document.getElementById('wbCalTlBody'));
            document.getElementById('wbCalTlBody').removeEventListener('contextmenu', _onAgendaContextMenu);
            document.getElementById('wbCalTlBody').addEventListener('contextmenu', _onAgendaContextMenu);
          }
        }).catch(() => {});
    }
  }, 5 * 60 * 1000);   // 5 分钟

  function _onAgendaContextMenu(e) {
    const item = e.target.closest('.wb-dv-ev-feishu');
    if (!item) return;
    e.preventDefault();
    e.stopPropagation();
    _showEventCtxMenu(e.clientX, e.clientY,
      item.dataset.eventId, item.dataset.isOrganizer === '1',
      item.dataset.rsvp, item, item.dataset.meetingUrl || '');
  }

  // ── 日程右键菜单 ──────────────────────────────────────────────────────────
  let _evtCtxCleanup = null;

  function _showEventCtxMenu(x, y, eventId, isOrganizer, curRsvp, itemEl, meetingUrl) {
    console.log('[EVT-CTX] show, eventId=', eventId, 'isOrg=', isOrganizer, 'rsvp=', curRsvp);
    const menu = document.getElementById('wbEvtCtxMenu');
    if (!menu) { console.warn('[EVT-CTX] #wbEvtCtxMenu not found'); return; }

    // ① 先清理旧 listener
    if (_evtCtxCleanup) {
      console.log('[EVT-CTX] cleaning up previous handlers');
      _evtCtxCleanup();
      _evtCtxCleanup = null;
    }

    const isIgnored = itemEl?.dataset.isIgnored === '1';
    const rsvpItems = [
      { status: 'accept',    label: '接受', icon: '✓', cls: 'accept'   },
      { status: 'tentative', label: '待定', icon: '~', cls: 'tentative' },
      { status: 'decline',   label: '拒绝', icon: '✗', cls: 'decline'  },
    ];

    menu.innerHTML = `
      ${meetingUrl ? `
        <div class="wb-evt-ctx-item join-item" data-action="join">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="flex-shrink:0">
            <rect x="1" y="4" width="10" height="8" rx="1" stroke="currentColor" stroke-width="1.4"/>
            <path d="M11 7l4-3v8l-4-3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
          </svg>加入会议
        </div>
        <div class="wb-evt-ctx-divider"></div>
      ` : ''}
      ${isIgnored ? '' : `
        <div class="wb-evt-ctx-section">回复邀请</div>
        ${rsvpItems.map(r => `
          <div class="wb-evt-ctx-item${curRsvp === r.status ? ' active' : ''}"
               data-action="rsvp" data-status="${r.status}">
            <span class="wb-evt-ctx-rsvp-icon ${r.cls}">${r.icon}</span>${r.label}
          </div>`).join('')}
      `}
      <div class="wb-evt-ctx-divider"></div>
      ${isIgnored
        ? `<div class="wb-evt-ctx-item" data-action="unignore">
             <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="flex-shrink:0">
               <path d="M2 8a6 6 0 1 0 12 0A6 6 0 0 0 2 8Z" stroke="currentColor" stroke-width="1.3"/>
               <path d="M6 8h4M8 6v4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
             </svg>取消忽略
           </div>`
        : `<div class="wb-evt-ctx-item ignore-item" data-action="ignore">
             <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="flex-shrink:0">
               <path d="M2 8a6 6 0 1 0 12 0A6 6 0 0 0 2 8Z" stroke="currentColor" stroke-width="1.3"/>
               <path d="M6 10L10 6M6 6l4 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
             </svg>忽略
           </div>`}
      ${isOrganizer && !isIgnored ? `
        <div class="wb-evt-ctx-item" data-action="edit">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style="flex-shrink:0">
            <path d="M2 12L6 11 13 4 12 3 5 10 2 12Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
          </svg>编辑日程
        </div>` : ''}
    `;

    // ② 内容填好再显示
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';
    menu.classList.remove('hidden');
    console.log('[EVT-CTX] menu visible=', !menu.classList.contains('hidden'));

    requestAnimationFrame(() => {
      const mw = menu.offsetWidth, mh = menu.offsetHeight;
      if (x + mw > window.innerWidth  - 8) menu.style.left = (x - mw) + 'px';
      if (y + mh > window.innerHeight - 8) menu.style.top  = (y - mh) + 'px';
    });

    const closeMenu = () => {
      console.log('[EVT-CTX] closeMenu');
      menu.classList.add('hidden');
      menu.removeEventListener('click', onClick);
      document.removeEventListener('mousedown', onOutside, true);
      document.removeEventListener('keydown', onEsc, true);
      if (_evtCtxCleanup === closeMenu) _evtCtxCleanup = null;
    };
    const onClick = (e) => {
      const actionEl = e.target.closest('[data-action]');
      if (!actionEl) return;
      console.log('[EVT-CTX] click action=', actionEl.dataset.action, actionEl.dataset.status || '');
      if (actionEl.dataset.action === 'join') {
        if (meetingUrl) {
          const api = window.electronAPI || window.parent?.electronAPI;
          if (api?.openWebpage) api.openWebpage(meetingUrl);
          else window.open(meetingUrl, '_blank');
        }
      } else if (actionEl.dataset.action === 'rsvp') {
        _handleEventRsvp(eventId, actionEl.dataset.status, itemEl);
      } else if (actionEl.dataset.action === 'edit') {
        _openEventEditModal(eventId, itemEl);
      } else if (actionEl.dataset.action === 'ignore') {
        _ignoredEvts.add(eventId);
        _saveIgnored();
        _loadFeishuAgenda();
        window.parent?.TaskTimeline?.refresh?.();
      } else if (actionEl.dataset.action === 'unignore') {
        _ignoredEvts.delete(eventId);
        _saveIgnored();
        _loadFeishuAgenda();
        window.parent?.TaskTimeline?.refresh?.();
      }
      closeMenu();
    };
    const onOutside = (e) => { if (!menu.contains(e.target)) closeMenu(); };
    const onEsc = (e) => { if (e.key === 'Escape') closeMenu(); };

    _evtCtxCleanup = closeMenu;
    menu.addEventListener('click', onClick);
    setTimeout(() => {
      document.addEventListener('mousedown', onOutside, true);
      document.addEventListener('keydown', onEsc, true);
    }, 10);
  }

  function _showRsvpAuthPrompt() {
    // 找日历面板容器，在其内追加提示条（单例）
    const existing = document.getElementById('wbRsvpAuthBanner');
    if (existing) return;
    const container = document.querySelector('.wb-cal-agenda') || document.querySelector('.wb-widget-body');
    if (!container) {
      alert('回复日程需要重新授权飞书日历权限，请点击设置 → 退出登录后重新登录。');
      return;
    }
    const banner = document.createElement('div');
    banner.id = 'wbRsvpAuthBanner';
    banner.style.cssText = `
      display:flex;align-items:center;gap:8px;padding:8px 10px;margin:6px 0;
      background:var(--bg-warning,#fef9c3);border:1px solid var(--border-warning,#fde68a);
      border-radius:6px;font-size:12px;color:var(--text-primary);
    `;
    banner.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="flex-shrink:0">
        <path d="M8 2L1 14h14L8 2Z" stroke="#ca8a04" stroke-width="1.4" stroke-linejoin="round"/>
        <path d="M8 7v3M8 11.5v.5" stroke="#ca8a04" stroke-width="1.4" stroke-linecap="round"/>
      </svg>
      <span style="flex:1">回复日程需要日历写权限，需重新授权飞书登录</span>
      <button id="wbRsvpReauthBtn" style="
        padding:3px 10px;border-radius:4px;font-size:12px;cursor:pointer;
        background:var(--accent-color,#4f7ef8);color:#fff;border:none;
      ">重新授权</button>
      <button id="wbRsvpBannerClose" style="
        background:none;border:none;cursor:pointer;color:var(--text-secondary);font-size:14px;padding:0 2px;
      ">✕</button>
    `;
    container.insertBefore(banner, container.firstChild);
    document.getElementById('wbRsvpBannerClose').onclick = () => banner.remove();
    document.getElementById('wbRsvpReauthBtn').onclick = () => {
      banner.remove();
      // 触发飞书重新登录（会弹出新的授权页面，用户同意后刷新 token）
      if (window.electronAPI?.authFeishuLogin) {
        window.electronAPI?.authFeishuLogin?.();
      } else if (window.parent?.electronAPI?.authFeishuLogin) {
        window.parent.electronAPI?.authFeishuLogin?.();
      } else {
        alert('请点击应用设置 → 退出登录，然后重新飞书登录以授权日历权限。');
      }
    };
  }

  async function _handleEventRsvp(eventId, status, itemEl) {
    if (!eventId) return;
    const cf = window._cloudFetch || window.parent?._cloudFetch;
    if (!cf) return;
    try {
      const res = await cf(`/feishu/calendar/events/${eventId}/rsvp`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rsvp_status: status }),
      });
      if (res?.success === false) {
        console.warn('[RSVP]', res.msg || res.error);
        // 权限不足 → 提示重新授权
        if (res.msg && (res.msg.includes('99991679') || res.msg.includes('privilege'))) {
          _showRsvpAuthPrompt();
        }
        return;
      }
      // 更新 item 元素上的 RSVP 指示
      if (itemEl) {
        itemEl.dataset.rsvp = status;
        const rsvpLabel = { accept: '✓', decline: '✗', needs_action: '?', tentative: '~' };
        const rsvpClass = { accept: 'accept', decline: 'decline', needs_action: 'pending', tentative: 'tentative' };
        const rsvpBg   = { accept: '#a6e3a1', decline: '#f38ba8', pending: '#f9e2af', tentative: '#89b4fa44' };
        const lbl = rsvpLabel[status] || '?';
        const cls = rsvpClass[status] || 'pending';
        const bg  = rsvpBg[cls] || '#f9e2af';
        // 日视图（.wb-dv-ev-feishu）：第一个 span 是 rsvp badge
        if (itemEl.classList.contains('wb-dv-ev-feishu')) {
          const badge = itemEl.querySelector('span');
          if (badge) {
            badge.textContent = lbl;
            badge.style.background = bg;
          }
        } else {
          // 旧列表视图（.wb-cal-agenda-item）
          const span = itemEl.querySelector('.wb-cal-agenda-rsvp');
          if (span) {
            span.className = `wb-cal-agenda-rsvp ${cls}`;
            span.textContent = lbl;
          }
        }
      }
      // 更新内存缓存并刷新 day-view + 状态栏
      if (_calFeishuItems) {
        const ev = _calFeishuItems.find(e => e.event_id === eventId);
        if (ev) ev.rsvp = status;
      }
      _refreshDayView();
      window.parent?.TaskTimeline?.refresh?.();
    } catch (err) {
      console.error('[RSVP] 异常:', err);
    }
  }

  async function _openEventEditModal(eventId, itemEl) {
    console.log('[EVT-EDIT] open, eventId=', eventId);
    const modal = document.getElementById('wbEvtEditModal');
    if (!modal || !eventId) { console.warn('[EVT-EDIT] modal not found or no eventId'); return; }
    const cf = window._cloudFetch || window.parent?._cloudFetch;
    const summaryEl  = document.getElementById('wbEvtEditSummary');
    const descEl     = document.getElementById('wbEvtEditDesc');
    const saveBtn    = document.getElementById('wbEvtEditSave');
    const closeBtn   = document.getElementById('wbEvtEditClose');
    const cancelBtn  = document.getElementById('wbEvtEditCancel');
    const errEl      = document.getElementById('wbEvtEditErr');
    console.log('[EVT-EDIT] elements:', { summaryEl, descEl, saveBtn, closeBtn, cancelBtn, errEl });

    summaryEl.value     = itemEl?.dataset.summary || '';
    descEl.value        = itemEl?.dataset.description || '';
    errEl.textContent   = '';
    saveBtn.disabled    = false;
    saveBtn.textContent = '保存';
    modal.classList.remove('hidden');
    console.log('[EVT-EDIT] modal shown, hidden=', modal.classList.contains('hidden'));

    // ① onclick 赋值必须在 await 之前，避免被后续调用覆盖
    const close = () => {
      console.log('[EVT-EDIT] close called');
      modal.classList.add('hidden');
    };
    closeBtn.onclick  = close;
    if (cancelBtn) cancelBtn.onclick = close;

    saveBtn.onclick = async () => {
      console.log('[EVT-EDIT] save clicked, eventId=', eventId);
      const summary     = summaryEl.value.trim();
      const description = descEl.value;
      if (!summary) { errEl.textContent = '标题不能为空'; return; }
      if (!cf) { errEl.textContent = '网络不可用'; return; }
      saveBtn.disabled    = true;
      saveBtn.textContent = '保存中…';
      try {
        const res = await cf(`/feishu/calendar/events/${eventId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ summary, description }),
        });
        console.log('[EVT-EDIT] save result:', res);
        if (res?.success === false) {
          errEl.textContent   = res.msg || res.error || '保存失败';
          saveBtn.disabled    = false;
          saveBtn.textContent = '保存';
        } else {
          if (itemEl) {
            itemEl.dataset.summary     = summary;
            itemEl.dataset.description = description;
            const titleEl = itemEl.querySelector('.wb-cal-agenda-title');
            if (titleEl) titleEl.textContent = summary;
          }
          close();
        }
      } catch (err) {
        console.error('[EVT-EDIT] save error:', err);
        errEl.textContent   = '请求失败';
        saveBtn.disabled    = false;
        saveBtn.textContent = '保存';
      }
    };

    // ② await 在 onclick 赋值之后——即使网络慢也不会覆盖已绑定的 handler
    if (cf) {
      try {
        const r = await cf(`/feishu/calendar/events/${eventId}`);
        console.log('[EVT-EDIT] detail fetched:', r?.success, r?.event?.summary);
        if (r?.success && r.event) {
          summaryEl.value = r.event.summary || summaryEl.value;
          descEl.value    = r.event.description || descEl.value;
        }
      } catch (_) {}
    }

    summaryEl.focus();
  }

  // ── 右侧通知栏按需加载 ───────────────────────────────────────────────────
  async function _loadRightPanel(panel) {
    const fn = _cf();
    if (!fn) return;
    // panel 5: follows（已在 home 数据里）
    // panel 6/7: 占位，后续补充 API
    if (panel === 4 && _panelData[4]) {
      _renderPanelFollows(_panelData[4]);
    } else if (panel === 5) {
      _renderPanelAlerts([]);
    } else if (panel === 6) {
      _renderPanelStatus([]);
    }
  }

  // ── 数据加载 ─────────────────────────────────────────────────────────────

  // 面板1 独立加载（使用 /api/workbench/panel1，支持多来源）
  async function _loadPanel1() {
    const fn = _cf(); if (!fn) return;
    const body = document.getElementById('wb-p1-today');
    if (body) body.innerHTML = '<div class="wb-loading">加载中…</div>';
    try {
      // 过滤掉前端专属来源（feishu 由前端直接拉取，不经过 panel1 API）
      const _apiSources = (_p1Settings.sources || ['task', 'issue']).filter(v => {
        const d = _P1_DOMAINS.find(x => x.value === v);
        return d && !d.calOnly;
      });
      const sources = _apiSources.join(',') || 'task';
      const params = new URLSearchParams({ sources });
      const lf = _p1Settings.listFilter || {};
      for (const domain of ['task', 'issue', 'knowledge', 'rule']) {
        if (Array.isArray(lf[domain]) && lf[domain].length > 0) {
          params.set(`${domain}_lists`, lf[domain].join(','));
        }
      }
      // BOP：gid 前缀区分 bv:(BOP版本) 和 pv:(PBOM版本)
      if (Array.isArray(lf.bop) && lf.bop.length > 0) {
        const bvGids = lf.bop.filter(g => g.startsWith('bv:')).map(g => g.slice(3));
        const pvGids = lf.bop.filter(g => g.startsWith('pv:')).map(g => g.slice(3));
        if (bvGids.length) params.set('bop_version_gids', bvGids.join(','));
        if (pvGids.length) params.set('pbom_version_gids', pvGids.join(','));
      }
      const data = await fn(`/api/workbench/panel1?${params}`);
      _panelData[1] = data.items || [];
      _renderPanelToday(_panelData[1]);
      if (_vis.cal) _renderCalendar();  // 同步刷新时间线
    } catch (e) {
      console.error('面板1加载失败', e);
      const b = document.getElementById('wb-p1-today');
      if (b) b.innerHTML = '<div class="wb-empty">加载失败，请刷新</div>';
    }
  }

  async function _loadHome() {
    _panel1ListsCache = null;  // 刷新时清除清单缓存
    const fn = _cf();
    if (!fn) {
      const ids = ['wb-body-1','wb-body-2','wb-body-3','wb-body-4','wb-body-5','wb-body-6'];
      ids.forEach(id => {
        const b = document.getElementById(id);
        if (b) b.innerHTML = '<div class="wb-empty">请先登录</div>';
      });
      return;
    }
    // 面板1 与主数据并行加载
    _loadPanel1();
    try {
      const data = await fn('/api/workbench/home');
      // _panelData[1] 由 _loadPanel1 管理，不再使用 today_items
      _panelData[3] = data.my_contexts     || [];
      _panelData[4] = data.recent_follows  || [];
      _panelData[5] = data.alerts          || [];
      _panelData[6] = [];

      _renderPanel(2);
      _renderPanel(3);
      if (_vis[4]) _renderPanel(4);
      if (_vis[5]) _renderPanel(5);
      if (_vis[6]) _renderPanel(6);
      if (_vis.cal) _renderCalendar();

      _updateStatusbar(); // 刷新徽标计数
    } catch (e) {
      console.error('工作台加载失败', e);
      ['wb-body-3'].forEach(id => {
        const b = document.getElementById(id);
        if (b) b.innerHTML = '<div class="wb-empty">加载失败，请刷新</div>';
      });

    }
  }

  // ── 打开页签 ──────────────────────────────────────────────────────────────
  function _openTab(viewId, params) {
    const tm = window.parent?.TabManager;
    if (tm) tm.open(viewId, params);
    else window.parent?.postMessage({ type: 'open-tab', viewId, params }, '*');
  }

  // ── 工具 ─────────────────────────────────────────────────────────────────
  function _setCount(panel, filtered, total) {
    const el = document.getElementById(`wb-count-${panel}`);
    if (!el) return;
    if (total > 0) {
      el.textContent = filtered < total ? `${filtered}/${total}` : String(total);
      el.classList.add('visible');
    } else {
      el.classList.remove('visible');
    }
  }

  // ── 面板1 新建条目 Modal ───────────────────────────────────────────────────
  function _getNiListOptions(domain) {
    const filter = (_p1Settings.listFilter || {})[domain] || [];
    let lists = (_panel1ListsCache || []).filter(l => l.item_type === domain);
    if (filter.length > 0) {
      const filterSet = new Set(filter);
      lists = lists.filter(l => filterSet.has(l.gid));
    }
    return lists;
  }

  async function _submitNewItemByDomain(domain, listGid, fields) {
    const fn = _cf();
    if (!fn) throw new Error('未连接到服务器');
    const uid = _currentUser?.gid || '';
    const body = { ...fields, list_gid: listGid || null };
    switch (domain) {
      case 'task':
        body.owner_gid = uid; body.owner_user_gid = uid;
        body.status = 'pending';
        return fn('/api/tasks', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      case 'issue':
        body.owner_gid = uid; body.owner_user_gid = uid;
        body.status = 'open';
        return fn('/api/issues', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      case 'knowledge':
        body.maintainer_gid = uid; body.status = 'draft';
        return fn('/api/knowledge_entries', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      case 'rule':
        body.status = 'draft';
        return fn('/api/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      default:
        throw new Error('不支持的域：' + domain);
    }
  }

  function _onNiDomainChange(domain) {
    const listSel   = document.getElementById('wbNiList');
    const listRow   = document.getElementById('wbNiListRow');
    const fieldsEl  = document.getElementById('wbNiFields');
    const bopHint   = document.getElementById('wbNiBopHint');
    const submitBtn = document.getElementById('wbNiSubmit');

    const isBop = domain === 'bop';
    bopHint.classList.toggle('hidden', !isBop);
    fieldsEl.classList.toggle('hidden', isBop);
    submitBtn.classList.toggle('hidden', isBop);
    listRow.classList.toggle('hidden', isBop);

    if (isBop) return;

    const lists = _getNiListOptions(domain);
    listSel.innerHTML = lists.length
      ? lists.map(l => `<option value="${l.gid}">${l.name}</option>`).join('')
      : `<option value="">（无清单）</option>`;

    const defs = _NI_DOMAIN_FIELDS[domain] || [];
    fieldsEl.innerHTML = defs.map(f => {
      const label = `<label class="wb-ni-label">${f.label}</label>`;
      let input;
      if (f.type === 'text') {
        input = `<input type="text" data-ni-key="${f.key}" placeholder="${f.required ? '必填' : ''}" autocomplete="off">`;
      } else if (f.type === 'select') {
        input = `<select data-ni-key="${f.key}">${f.options.map(([v,t]) =>
          `<option value="${v}"${v===f.def?' selected':''}>${t}</option>`).join('')}</select>`;
      } else if (f.type === 'date') {
        input = `<input type="date" data-ni-key="${f.key}">`;
      } else if (f.type === 'num_presets') {
        const presetBtns = f.presets.map(p =>
          `<button type="button" class="wb-ni-preset${p===f.def?' active':''}" data-ni-preset="${f.key}" data-val="${p}">${p}</button>`
        ).join('');
        input = `<div class="wb-ni-num-group">${presetBtns}<input class="wb-ni-num-inp" type="number" data-ni-key="${f.key}" value="${f.def??''}" min="1" step="5" placeholder="分"></div>`;
      }
      return `<div class="wb-ni-field-row">${label}${input}</div>`;
    }).join('');

    fieldsEl.querySelector('input[type="text"]')?.focus();
  }

  function _initNewItemModal() {
    const overlay   = document.getElementById('wbNewItemModal');
    const domSel    = document.getElementById('wbNiDomain');
    const fieldsEl  = document.getElementById('wbNiFields');
    const errEl     = document.getElementById('wbNiError');
    const submitBtn = document.getElementById('wbNiSubmit');

    const _close = () => overlay.classList.add('hidden');
    document.getElementById('wbNiCancel').addEventListener('click', _close);
    document.getElementById('wbNiClose').addEventListener('click', _close);
    overlay.addEventListener('click', e => { if (e.target === overlay) _close(); });

    // 预设按钮委托（动态渲染后依然有效）
    fieldsEl.addEventListener('click', e => {
      const btn = e.target.closest('[data-ni-preset]');
      if (!btn) return;
      const key = btn.dataset.niPreset;
      const val = btn.dataset.val;
      const inp = fieldsEl.querySelector(`[data-ni-key="${key}"]`);
      if (inp) inp.value = val;
      fieldsEl.querySelectorAll(`[data-ni-preset="${key}"]`).forEach(b => b.classList.toggle('active', b === btn));
    });
    // 手动输入数字时同步预设按钮高亮
    fieldsEl.addEventListener('input', e => {
      const inp = e.target.closest('input[type="number"][data-ni-key]');
      if (!inp) return;
      const key = inp.dataset.niKey, val = inp.value.trim();
      fieldsEl.querySelectorAll(`[data-ni-preset="${key}"]`).forEach(b =>
        b.classList.toggle('active', b.dataset.val === val));
    });

    document.getElementById('wbNiBopLink')?.addEventListener('click', () => {
      _close();
      const bopFilter = (_p1Settings.listFilter || {}).bop || [];
      const firstBv = bopFilter.find(g => g.startsWith('bv:'));
      if (firstBv) _openTab('lineage_view', { bop_version_gid: firstBv.slice(3) });
    });

    domSel.addEventListener('change', () => _onNiDomainChange(domSel.value));

    submitBtn.addEventListener('click', async () => {
      errEl.classList.add('hidden');
      const domain  = domSel.value;
      const listGid = document.getElementById('wbNiList').value || null;
      const defs    = _NI_DOMAIN_FIELDS[domain] || [];
      const data    = {};
      let valid     = true;
      for (const f of defs) {
        const el  = fieldsEl.querySelector(`[data-ni-key="${f.key}"]`);
        const val = el?.value?.trim() || '';
        if (f.required && !val) {
          errEl.textContent = `${f.label} 不能为空`;
          errEl.classList.remove('hidden');
          el?.focus();
          valid = false; break;
        }
        if (val) data[f.key] = val;
      }
      if (!valid) return;
      submitBtn.disabled = true;
      try {
        await _submitNewItemByDomain(domain, listGid, data);
        _close();
        _panel1ListsCache = null;
        await _loadPanel1();
      } catch (e) {
        errEl.textContent = '创建失败：' + (e?.message || String(e));
        errEl.classList.remove('hidden');
      } finally { submitBtn.disabled = false; }
    });

    overlay.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.stopPropagation(); _close(); }
    });
  }

  function _openNewItemModal() {
    const overlay = document.getElementById('wbNewItemModal');
    const domSel  = document.getElementById('wbNiDomain');
    const errEl   = document.getElementById('wbNiError');
    errEl.classList.add('hidden');

    const activeDomains = (_p1Settings.sources || ['task', 'issue']).filter(v => {
      const d = _P1_DOMAINS.find(x => x.value === v);
      return d && !d.calOnly;  // 飞书日历不能新建条目
    });
    domSel.innerHTML = activeDomains.map(v => {
      const d = _P1_DOMAINS.find(x => x.value === v);
      return `<option value="${v}">${d?.label || v}</option>`;
    }).join('');

    const defaultDomain = activeDomains.find(v => v !== 'bop') || activeDomains[0];
    domSel.value = defaultDomain;
    _onNiDomainChange(defaultDomain);

    overlay.classList.remove('hidden');
  }

  // ── 新建任务（旧，保留兼容）────────────────────────────────────────────────
  async function _createNew() {
    const title = await _promptText('新建任务', '');
    if (!title) return;
    const fn = _cf();
    if (!fn) return;
    try {
      await fn('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          owner_user_gid: _currentUser?.gid || '',
          owner_gid:      _currentUser?.gid || '',
          status: 'todo', priority: 'medium',
        }),
      });
      await _loadHome();
    } catch (e) { console.error('新建任务失败', e); }
  }

  // ── Modal 工具 ────────────────────────────────────────────────────────────
  function _promptText(title, defaultVal) {
    return new Promise(resolve => {
      const overlay   = document.getElementById('wbInputModal');
      const titleEl   = document.getElementById('wbInputModalTitle');
      const field     = document.getElementById('wbInputModalField');
      const okBtn     = document.getElementById('wbInputModalOk');
      const cancelBtn = document.getElementById('wbInputModalCancel');
      const closeBtn  = document.getElementById('wbInputModalClose');
      titleEl.textContent = title;
      field.value = defaultVal || '';
      overlay.classList.remove('hidden');
      field.focus();
      const done = (val) => {
        overlay.classList.add('hidden');
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        closeBtn.removeEventListener('click', onCancel);
        field.removeEventListener('keydown', onKey);
        resolve(val);
      };
      const onOk     = () => done(field.value.trim());
      const onCancel = () => done(null);
      const onKey    = (e) => {
        if (e.key === 'Enter')  done(field.value.trim());
        if (e.key === 'Escape') done(null);
      };
      okBtn.addEventListener('click', onOk);
      cancelBtn.addEventListener('click', onCancel);
      closeBtn.addEventListener('click', onCancel);
      field.addEventListener('keydown', onKey);
    });
  }

  // ── App 面板 ───────────────────────────────────────────────────────────────
  const _LS_APP = 'wb:app-items-v1';

  const _ALL_APP_ITEMS = [
    { id: 'workbench',      title: '工作台',     icon: 'icon-home',       requiresAuth: false },
    { id: 'my_files',       title: '我的文件',   icon: 'icon-files',      requiresAuth: false },
    { id: 'craft_hub',      title: '工艺规划',   icon: 'icon-canvas',     requiresAuth: true,  minPerm: 'craft.view' },
    { id: 'project_hub',    title: '项目管理',   icon: 'icon-project',    requiresAuth: false, minPerm: 'project.view' },
    { id: 'knowledge_hub',  title: '知识库',     icon: 'icon-knowledge',  requiresAuth: false },
    { id: 'automation_hub', title: '自动化与AI', icon: 'icon-robot',      requiresAuth: false },
    { id: 'ai_chat',        title: 'AI 对话',    icon: 'icon-robot',      requiresAuth: false },
    { id: 'wfc_canvas',     title: 'AI 画布',    icon: 'icon-canvas',     requiresAuth: false },
    { id: 'cad_sim',        title: '数模仿真',   icon: 'icon-cube',       requiresAuth: false },
    { id: 'admin_hub',      title: '管理中心',   icon: 'icon-org',        requiresAuth: true,  minPerm: 'system.user.manage' },
    { id: 'ontology',       title: '本体编辑器', icon: 'icon-onto',       requiresAuth: true,  minPerm: 'system.tech_config' },
    { id: 'ext_datasource', title: '外部数据源', icon: 'icon-datasource', requiresAuth: true,  minPerm: 'system.tech_config' },
    { id: 'handbook',       title: '帮助手册',   icon: 'icon-help',       requiresAuth: false },
  ];

  let _appState = null;

  function _loadAppState() {
    try {
      const s = JSON.parse(localStorage.getItem(_lsk(_LS_APP)) || '{}');
      if (Array.isArray(s.visible)) {
        const allIds = _ALL_APP_ITEMS.map(i => i.id);
        const vis = [...new Set(s.visible)].filter(id => allIds.includes(id));
        // 补充新模块
        allIds.filter(id => !vis.includes(id) && !(s.hidden || []).includes(id))
              .forEach(id => vis.push(id));
        const hid = allIds.filter(id => !vis.includes(id));
        return { visible: vis, hidden: hid };
      }
    } catch (_) {}
    return { visible: _ALL_APP_ITEMS.map(i => i.id), hidden: [] };
  }

  function _saveAppState() {
    localStorage.setItem(_lsk(_LS_APP), JSON.stringify(_appState));
  }

  function _getAppItem(id) { return _ALL_APP_ITEMS.find(i => i.id === id); }

  function _appItemAllowed(item) {
    const authMode = window.parent?._authMode || window._authMode || 'none';
    if (authMode !== 'feishu' && item.requiresAuth) return false;
    if (item.minPerm) {
      const fn = window.parent?._hasTabPerm;
      if (typeof fn === 'function' && !fn(item.minPerm)) return false;
    }
    // feature_flags 可见性控制
    const flags = window.parent?._featureFlags || {};
    const ff = flags['app_' + item.id];
    if (ff?.visibility) {
      const fn = window.parent?._meetsRoleLevel;
      if (typeof fn === 'function' && !fn(ff.visibility)) return false;
    }
    return true;
  }

  function _appItemEnabled(item) {
    const flags = window.parent?._featureFlags || {};
    const ff = flags['app_' + item.id];
    if (ff?.availability) {
      const fn = window.parent?._meetsRoleLevel;
      if (typeof fn === 'function' && !fn(ff.availability)) return false;
    }
    return true;
  }

  // 9 点图标 SVG
  const _GRID9_SVG =
    '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">' +
    '<circle cx="2" cy="2" r="1.3"/><circle cx="7" cy="2" r="1.3"/><circle cx="12" cy="2" r="1.3"/>' +
    '<circle cx="2" cy="7" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="12" cy="7" r="1.3"/>' +
    '<circle cx="2" cy="12" r="1.3"/><circle cx="7" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/>' +
    '</svg>';

  function _renderAppPanel() {
    const grid = document.getElementById('wbAppGrid');
    if (!grid) return;
    if (!_appState) _appState = _loadAppState();

    grid.innerHTML = '';

    // ── 设置按钮（固定第一）──────────────────────────────────────
    const settingsBtn = document.createElement('button');
    settingsBtn.className = 'wb-app-item';
    settingsBtn.title = '系统设置';
    settingsBtn.innerHTML =
      '<svg class="icon" width="16" height="16"><use href="#icon-settings"/></svg>' +
      '<span>设置</span>';
    settingsBtn.addEventListener('click', () => {
      // 判断是否运行在网页版（父窗口的 electronAPI._isElectron === false）
      const isWeb = window.parent?.electronAPI?._isElectron === false;
      if (isWeb) {
        window.parent?.postMessage({ type: 'open-overlay', src: '/web/settings/index.html', title: '系统设置' }, '*');
      } else {
        window.parent?.TabManager?.open('settings');
      }
    });
    grid.appendChild(settingsBtn);

    // ── 可见模块（用户可排序/隐藏）──────────────────────────────
    _appState.visible.forEach((id, idx) => {
      const item = _getAppItem(id);
      if (!item || !_appItemAllowed(item)) return;

      const btn = document.createElement('button');
      btn.className = 'wb-app-item';
      btn.dataset.appId = id;
      btn.innerHTML =
        `<svg class="icon" width="16" height="16"><use href="#${item.icon}"/></svg>` +
        `<span>${item.title}</span>`;

      const enabled = _appItemEnabled(item);
      if (!enabled) {
        btn.disabled = true;
        btn.style.opacity = '0.4';
        btn.style.cursor  = 'not-allowed';
        btn.title = item.title + '（权限不足）';
      } else {
        btn.title = item.title;
        btn.addEventListener('click', () => {
          window.parent?.postMessage({ type: 'tab:open', id: item.id }, '*');
        });
      }
      btn.addEventListener('contextmenu', e => { e.preventDefault(); _showAppCtxMenu(e, id, idx); });
      grid.appendChild(btn);
    });

    // ── 更多按钮（有隐藏项时显示）──────────────────────────────
    const hasHidden = _appState.hidden.some(id => {
      const it = _getAppItem(id);
      return it && _appItemAllowed(it);
    });
    const moreBtn = document.createElement('button');
    moreBtn.className = 'wb-app-more';
    moreBtn.title = '更多 App';
    moreBtn.innerHTML = _GRID9_SVG + '<span>更多</span>';
    moreBtn.addEventListener('click', e => _showAppMorePopover(e));
    grid.appendChild(moreBtn);
  }

  function _showAppCtxMenu(e, id, visIdx) {
    document.getElementById('_wbAppCtx')?.remove();
    const vis  = _appState.visible;
    const menu = document.createElement('div');
    menu.id = '_wbAppCtx';
    menu.className = 'wb-app-ctx-menu';

    const isFirst = visIdx === 0;
    const isLast  = visIdx === vis.length - 1;
    const items = [
      { label: '↑ 上移',   cls: isFirst ? 'disabled' : '', action: () => { if (!isFirst) [vis[visIdx-1], vis[visIdx]] = [vis[visIdx], vis[visIdx-1]]; } },
      { label: '↓ 下移',   cls: isLast  ? 'disabled' : '', action: () => { if (!isLast)  [vis[visIdx+1], vis[visIdx]] = [vis[visIdx], vis[visIdx+1]]; } },
      { label: '从面板移除', cls: '', action: () => { _appState.visible.splice(visIdx, 1); _appState.hidden.push(id); } },
    ];

    items.forEach(it => {
      const el = document.createElement('div');
      el.className = `wb-app-ctx-item ${it.cls}`;
      el.textContent = it.label;
      if (!it.cls) el.addEventListener('click', () => { menu.remove(); it.action(); _saveAppState(); _renderAppPanel(); });
      menu.appendChild(el);
    });

    document.body.appendChild(menu);
    let x = e.clientX, y = e.clientY;
    if (x + 130 > window.innerWidth) x = window.innerWidth - 135;
    if (y + 100 > window.innerHeight) y = window.innerHeight - 105;
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';
    setTimeout(() => document.addEventListener('mousedown', function close(ev) {
      if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('mousedown', close); }
    }), 10);
  }

  function _showAppMorePopover(e) {
    document.getElementById('_wbAppMore')?.remove();
    const pop = document.createElement('div');
    pop.id = '_wbAppMore';
    pop.className = 'wb-app-more-popover';

    const hdr = document.createElement('div');
    hdr.className = 'wb-app-more-hdr';
    hdr.textContent = '隐藏的 App';
    pop.appendChild(hdr);

    const hidden = _appState.hidden.filter(id => {
      const it = _getAppItem(id);
      return it && _appItemAllowed(it);
    });

    if (hidden.length === 0) {
      const empty = document.createElement('div');
      empty.style.cssText = 'padding:8px 6px;font-size:12px;color:var(--text-muted);text-align:center;';
      empty.textContent = '所有 App 均已显示';
      pop.appendChild(empty);
    } else {
      hidden.forEach(id => {
        const item = _getAppItem(id);
        if (!item) return;
        const row = document.createElement('div');
        row.className = 'wb-app-more-item';
        row.innerHTML =
          `<svg class="icon" width="14" height="14"><use href="#${item.icon}"/></svg>` +
          `<span style="flex:1">${item.title}</span>`;
        const addBtn = document.createElement('button');
        addBtn.className = 'wb-app-more-add';
        addBtn.title = '添加到面板';
        addBtn.textContent = '+';
        addBtn.addEventListener('click', e2 => {
          e2.stopPropagation();
          _appState.hidden = _appState.hidden.filter(x => x !== id);
          _appState.visible.push(id);
          _saveAppState();
          _renderAppPanel();
          pop.remove();
        });
        row.appendChild(addBtn);
        row.addEventListener('click', () => { window.parent?.TabManager?.open(id); pop.remove(); });
        pop.appendChild(row);
      });
    }

    document.body.appendChild(pop);
    const rect = e.currentTarget.getBoundingClientRect();
    let x = rect.left, y = rect.bottom + 4;
    if (x + 220 > window.innerWidth) x = window.innerWidth - 225;
    if (y + 200 > window.innerHeight) y = rect.top - pop.offsetHeight - 4;
    pop.style.left = x + 'px';
    pop.style.top  = y + 'px';
    setTimeout(() => document.addEventListener('mousedown', function close(ev) {
      if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener('mousedown', close); }
    }), 10);
  }

  // ── AI 聊天球 ─────────────────────────────────────────────────────────────
  function _initAiBall() {
    const ball = document.getElementById('wbFloatBall');
    const chat = document.getElementById('wbFloatChat');
    const closeBtn = document.getElementById('wbFcClose');
    const sendBtn  = document.getElementById('wbFcSend');
    const inp      = document.getElementById('wbFcInp');

    if (!ball || !chat) return;

    ball.addEventListener('click', () => {
      const open = chat.style.display !== 'none';
      chat.style.display = open ? 'none' : 'flex';
      if (!open) { _updateAiCtx(); inp?.focus(); }
      _syncAiBallToggleBtn();
    });

    closeBtn?.addEventListener('click', () => { chat.style.display = 'none'; _syncAiBallToggleBtn(); });

    // 状态栏 R 小柔按钮
    document.getElementById('wbAiBallToggleBtn')?.addEventListener('click', () => {
      const open = chat.style.display !== 'none';
      chat.style.display = open ? 'none' : 'flex';
      if (!open) { _updateAiCtx(); inp?.focus(); }
      _syncAiBallToggleBtn();
    });

    function _syncAiBallToggleBtn() {
      const btn = document.getElementById('wbAiBallToggleBtn');
      if (!btn) return;
      const open = chat.style.display !== 'none';
      btn.classList.toggle('wb-sb-visible', open);
    }
    sendBtn?.addEventListener('click', _sendAiMsg);
    inp?.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _sendAiMsg(); }
      if (e.key === 'Escape') { inp.blur(); e.preventDefault(); }
    });

    // 聊天窗 tab 切换
    chat.querySelectorAll('.wb-fc-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        chat.querySelectorAll('.wb-fc-tab').forEach(t => t.classList.toggle('active', t === btn));
        document.getElementById('wbFcPaneChat') ?.classList.toggle('hidden', tab !== 'chat');
        document.getElementById('wbFcPaneSkill')?.classList.toggle('hidden', tab !== 'skill');
        document.getElementById('wbFcPaneTopic')?.classList.toggle('hidden', tab !== 'topic');
        if (tab === 'skill') _loadSkillList();
      });
    });
  }

  function _loadSkillList() {
    const body = document.getElementById('wbFcSkillBody');
    if (!body || body.dataset.loaded) return;
    const fn = _cf();
    if (!fn) return;
    fn('/api/skills?limit=50').then(data => {
      const skills = Array.isArray(data) ? data : (data?.skills || []);
      if (!skills.length) { body.innerHTML = '<div class="wb-fc-empty">暂无 Skill</div>'; return; }
      body.innerHTML = skills.map(s =>
        `<div class="wb-fc-skill-item" title="${_esc(s.description||'')}">⚡ ${_esc(s.name||s.title||'')}</div>`
      ).join('');
      body.dataset.loaded = '1';
    }).catch(() => {
      body.innerHTML = '<div class="wb-fc-empty">加载失败</div>';
    });
  }

  function _getAiCtx() {
    const parts = [];
    if (_focusedPanel === 1 && _selectedIdx[1] != null) {
      const rows = document.querySelectorAll('#wb-body-1 .wb-row');
      const row  = rows[_selectedIdx[1]];
      if (row) {
        try { const item = JSON.parse(row.dataset.item); parts.push(`当前任务：${item.title}（${item.status}）`); } catch(_){}
      }
    }
    if (_focusedPanel === 3 && _selectedIdx[3] != null) {
      const rows = document.querySelectorAll('#wb-body-3 .wb-row');
      const row  = rows[_selectedIdx[3]];
      if (row && row.dataset.projectGid) {
        const proj = (_panelData[3] || []).find(c => c.project_gid === row.dataset.projectGid);
        if (proj) parts.push(`当前项目：${proj.project_name}`);
      }
    }
    return parts.join('\n');
  }

  function _updateAiCtx() {
    const bar = document.getElementById('wbFcCtxBar');
    if (!bar) return;
    bar.textContent = _getAiCtx();
  }

  async function _sendAiMsg() {
    const inp  = document.getElementById('wbFcInp');
    const msgs = document.getElementById('wbFcMsgs');
    if (!inp || !msgs) return;
    const text = inp.value.trim();
    if (!text) return;
    inp.value = '';
    inp.disabled = true;

    // 清除空态
    const empty = msgs.querySelector('.wb-fc-empty');
    if (empty) empty.remove();

    // 追加用户气泡
    const userBubble = document.createElement('div');
    userBubble.className = 'wb-fc-msg user';
    userBubble.innerHTML = `<div class="wb-fc-bubble">${_esc(text)}</div>`;
    msgs.appendChild(userBubble);

    // AI 气泡（loading）
    const aiBubble = document.createElement('div');
    aiBubble.className = 'wb-fc-msg ai';
    const aiBubbleInner = document.createElement('div');
    aiBubbleInner.className = 'wb-fc-bubble';
    aiBubbleInner.textContent = '…';
    aiBubble.appendChild(aiBubbleInner);
    msgs.appendChild(aiBubble);
    msgs.scrollTop = msgs.scrollHeight;

    const eAPI = window.electronAPI || window.parent?.electronAPI;
    const config = await eAPI?.getConfig?.().catch?.(() => ({})) || {};
    const state  = await eAPI?.authGetState?.().catch?.(() => ({})) || {};
    const runtimeBase = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config.backendUrl || '')
    const baseUrl = (runtimeBase || config.backendUrl || '').replace(/\/$/, '');
    const token   = state.token || '';

    if (!token) {
      aiBubbleInner.textContent = '请先登录后再使用 AI 功能';
      inp.disabled = false;
      return;
    }

    try {
      const ctx = _getAiCtx();
      const body = { message: text, auth_token: token };
      if (ctx) body.context = ctx;

      // 使用 SSE 流式，边收边显示
      const res = await fetch(`${baseUrl}/api/ai/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-AI00-Token': token },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        aiBubbleInner.textContent = `请求失败：HTTP ${res.status}`;
        inp.disabled = false;
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let answer = '';
      aiBubbleInner.textContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === 'token') {
              answer += evt.content || '';
              aiBubbleInner.textContent = answer;
              msgs.scrollTop = msgs.scrollHeight;
            } else if (evt.type === 'error') {
              aiBubbleInner.textContent = '错误：' + (evt.message || '未知');
            }
          } catch (_) {}
        }
      }
      if (!answer) aiBubbleInner.textContent = '（无回复）';
    } catch (e) {
      aiBubbleInner.textContent = '请求失败：' + e.message;
    }

    inp.disabled = false;
    msgs.scrollTop = msgs.scrollHeight;
    _updateAiCtx();
  }

  // ── 初始化 ───────────────────────────────────────────────────────────────
  function _init() {
    _applyTheme();

    _currentUser = window.parent?._authUser || window._authUser || null;

    // 面板头部点击 → 聚焦
    document.querySelectorAll('.wb-panel-header').forEach(hdr => {
      hdr.addEventListener('click', () => {
        const p = +hdr.closest('.wb-panel')?.dataset.panel;
        if (p) _focusPanel(p);
      });
    });

    // 状态栏面板按钮
    document.querySelectorAll('.wb-sb-panel-btn').forEach(btn => {
      btn.addEventListener('click', () => _togglePanel(+btn.dataset.panel));
    });

    // App 面板按钮
    document.getElementById('wbAppBtn')?.addEventListener('click', () => _togglePanel('A'));

    // 日历按钮
    document.getElementById('wbCalBtn')?.addEventListener('click', _toggleCal);

    // 刷新
    document.getElementById('wbRefreshBtn')?.addEventListener('click', _loadHome);

    // 筛选输入
    _bindFilterInputs();

    // 面板3 详情条切换按钮
    document.getElementById('wb-p3-detail-toggle')?.addEventListener('click', () => _toggleDetailStrip('p3'));

    // ── 面板1 设置浮层 + 新建条目 Modal ─────────────────────────────
    _initP1SettingsPop();
    _initNewItemModal();

    // ── 面板2 设置浮层 + 新建按钮 + 搜索框 ──────────────────────────
    _initP2SettingsPop();
    _initP2NewBtn();
    const _p2SearchEl = document.getElementById('wb-p2-search');
    if (_p2SearchEl) {
      _p2SearchEl.addEventListener('input', () => {
        _p2SearchQuery = _p2SearchEl.value;
        if (_treeSections) _renderP2TreeSections(_treeSections);
      });
      _p2SearchEl.addEventListener('keydown', e => {
        if (e.key === 'Escape') { _p2SearchEl.value = ''; _p2SearchQuery = ''; if (_treeSections) _renderP2TreeSections(_treeSections); }
      });
    }

    // 面板1 今日 — 新建按钮
    document.getElementById('wb-p1-new-item')?.addEventListener('click', (e) => {
      e.stopPropagation();
      _openNewItemModal();
    });

    // 主题
    window.addEventListener('message', (e) => {
      if (e.data?.type === 'theme-change')          _applyTheme();
      if (e.data?.type === 'auth-state')            _renderAppPanel();
      if (e.data?.type === 'feature-flags-changed') _renderAppPanel();
    });

    // App 面板
    _renderAppPanel();

    // AI 球
    _initAiBall();

    // 左/中列分割条
    _initSplitter();
    // 今日/内容树内层分割条
    _initInnerSplitter();

    // 初始布局（先应用 vis，再加载数据）
    _switchCenterTab(_centerTab);
    _updateLayout();
    _updateStatusbar();

    // 进入工作台时自动聚焦第一个可见面板，键盘立即可用
    const autoFocus = [1, 2, 3].find(n => {
      if (n === 3) return _vis.center;
      return _vis[n];
    });
    if (autoFocus != null) _focusPanel(autoFocus);

    // 确保 iframe 获得键盘焦点（在 iframe 环境中需要 window.focus()）
    window.focus();
    document.body.focus();

    // 切换回工作台 tab 时重新获焦，键盘继续可用
    window.addEventListener('focus', () => { document.body.focus(); });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) document.body.focus();
    });

    // 加载数据
    _loadHome();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

})();
