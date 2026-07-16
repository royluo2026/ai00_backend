'use strict';
/**
 * EntryThread — 可复用的结构化条目渲染+CRUD 组件
 *
 * 模式：
 *   mode='ai'   — bug_tracker：AI/人图标 + 已读状态 + 复制AI指令 + 全权限按钮
 *   mode='human' — list_shell：显示用户名 + 无已读状态 + 权限化按钮
 *
 * 用法：
 *   const thread = new EntryThread({
 *     mountEl:          document.getElementById('entriesContainer'),
 *     mode:             'ai',           // 'ai' | 'human'
 *     entries:          [],              // 条目数组
 *     issueId:          '0000042',       // AI 模式下的问题编号
 *     currentUserGid:   '',              // human 模式：当前用户 gid
 *     userRole:         '',              // human 模式：当前用户角色
 *     listOwnerGid:     '',              // human 模式：清单 owner gid
 *     isCloud:          false,           // 是否云端条目
 *     onChange:         (entries) => {}, // 条目变更回调
 *     onSave:           async () => {},  // 持久化回调（Debounced by parent）
 *     onStatusMsg:      (msg) => {},     // 状态消息（复制等）
 *   });
 *   thread.setEntries(newEntries);  // 更新数据
 *   thread.collectTexts();          // 获取 textarea 内容同步到 entries
 *   thread.getEntries();            // 返回当前 entries
 */
class EntryThread {
  constructor(opts) {
    this._mountEl           = opts.mountEl;
    this._mode              = opts.mode || 'ai';
    this._editEntries       = JSON.parse(JSON.stringify(opts.entries || []));
    this._issueId           = opts.issueId || '';
    this._currentUserGid    = opts.currentUserGid || '';
    this._currentUserName   = opts.currentUserName || '';
    this._userRole          = opts.userRole || '';
    this._listOwnerGid      = opts.listOwnerGid || '';
    this._isCloud           = !!(opts.isCloud);
    this._onChange          = opts.onChange || (() => {});
    this._onSave            = opts.onSave || (() => {});
    this._onStatusMsg       = opts.onStatusMsg || (() => {});
    this._collapsedParents  = new Set();  // 折叠状态：被折叠的父卡片 ID 集合
    this._dragSrcId         = null;       // 当前拖拽中的条目 ID
  }

  // ─── 公开 API ──────────────────────────────────────────────────────────────

  setEntries(entries, issueId) {
    this._editEntries = JSON.parse(JSON.stringify(entries || []));
    if (issueId !== undefined) this._issueId = issueId;
    this._render();
  }

  getEntries() {
    return this._editEntries;
  }

  /** 同步所有 textarea 内容到 entries */
  collectTexts() {
    const cards = this._mountEl.querySelectorAll('.entry-card');
    cards.forEach(card => {
      const id = card.getAttribute('data-entry-id');
      const ta = card.querySelector('textarea');
      if (id && ta) {
        const e = this._editEntries.find(x => x.id === id);
        if (e) e.content = ta.value;
      }
    });
  }

  /** 迁移旧字段到 entries */
  static migrate(item) {
    if (Array.isArray(item.entries) && item.entries.length) return item.entries;
    const entries = [];
    let so = 1;
    const now = item.updated_at || item.created_at || new Date().toISOString();
    if ((item.detail || '').trim()) {
      entries.push({ id: EntryThread._genId(), parent_id: null, section: 'detail', author: 'human',
        content: item.detail.trim(), created_at: now, resolved: false, sort_order: so++,
        read_by_human: true, ai_status: 'unread' });
    }
    if ((item.ai_question || '').trim()) {
      entries.push({ id: EntryThread._genId(), parent_id: null, section: 'detail', author: 'ai',
        content: item.ai_question.trim(), created_at: now, resolved: false, sort_order: so++,
        read_by_human: false, ai_status: 'read' });
    }
    let hs = 1;
    if ((item.comment || '').trim()) {
      entries.push({ id: EntryThread._genId(), parent_id: null, section: 'history', author: 'human',
        content: item.comment.trim(), created_at: now, resolved: false, sort_order: hs++,
        read_by_human: true, ai_status: 'unread' });
    }
    if ((item.history || '').trim()) {
      entries.push({ id: EntryThread._genId(), parent_id: null, section: 'history', author: 'human',
        content: item.history.trim(), created_at: now, resolved: false, sort_order: hs++,
        read_by_human: true, ai_status: 'unread' });
    }
    return entries;
  }

  /** 从 entries 反推旧字段 */
  static entriesToOldFields(entries) {
    const detailEntries = (entries||[]).filter(e => e.section === 'detail').sort((a,b) => (a.sort_order||0)-(b.sort_order||0));
    const histEntries   = (entries||[]).filter(e => e.section === 'history').sort((a,b) => (a.sort_order||0)-(b.sort_order||0));
    return {
      detail:      detailEntries.filter(e => e.author === 'human').map(e => e.content).filter(Boolean).join('\n---\n'),
      ai_question: detailEntries.filter(e => e.author === 'ai').map(e => e.content).filter(Boolean).join('\n---\n'),
      comment:     histEntries.length ? histEntries[histEntries.length-1].content : '',
      history:     histEntries.map(e => `[${(e.created_at||'').slice(0,16)}] ${e.author==='ai'?'AI':'人'}: ${e.content}`).filter(x => x).join('\n'),
    };
  }

  // ─── 内部 ────────────────────────────────────────────────────────────────────

  _render() { this._renderCards('detail'); this._renderCards('history'); }

  _renderCards(section) {
    if (!this._mountEl) return;
    const targetId = section === 'detail' ? 'etDetailEntries' : 'etHistoryEntries';
    const countId  = section === 'detail' ? 'etDetailCount' : 'etHistoryCount';
    const el = this._mountEl.querySelector('#' + targetId);
    if (!el) return;
    const allEntries = this._editEntries
      .filter(e => {
        if (e.section !== section) return false;
        if (section === 'detail') return !e.resolved;
        return true;
      })
      .sort((a, b) => {
        if (section === 'history') {
          const rootA = this._getRootOrder(a);
          const rootB = this._getRootOrder(b);
          if (rootA !== rootB) return rootA - rootB;
          const depthA = this._entryDepth(a);
          const depthB = this._entryDepth(b);
          if (depthA !== depthB) return depthA - depthB;
        }
        return (a.sort_order || 0) - (b.sort_order || 0);
      });

    // 过滤掉被折叠的子孙卡片
    const visible = allEntries.filter(e => !this._hasCollapsedAncestor(e));
    // 总数（含被折叠的）
    const totalCount = allEntries.length;

    const countEl = this._mountEl.querySelector('#' + countId);
    if (countEl) {
      countEl.textContent = totalCount ? `${totalCount} 条` : '';
      if (totalCount) countEl.classList.add('has-items');
      else countEl.classList.remove('has-items');
    }

    // 计算层级编号（1, 1.1, 1.2, 2, 2.1, ...）
    const hierNum = this._computeHierNumbers(visible);

    const self = this;
    el.innerHTML = visible.map((e, i) => {
      const isReply = !!e.parent_id;
      const depth = self._entryDepth(e);  // 嵌套深度：0=主题, 1=回复, 2=回复的回复...
      const children = self._getChildren(e.id);
      const hasChildren = children.length > 0;
      const isCollapsed = self._collapsedParents.has(e.id);

      let cardCls = 'entry-card';
      if (isReply) cardCls += ' is-reply';
      if (depth > 0) cardCls += ' depth-' + depth;
      if (e.resolved) cardCls += ' resolved';
      if (hasChildren) cardCls += ' has-children';
      if (isCollapsed) cardCls += ' parent-collapsed';

      const eid = ET_esc(e.id);
      const esec = ET_esc(e.section);

      // collapse toggle for parent cards
      let collapseHtml = '';
      if (hasChildren) {
        const hiddenCount = self._getAllDescendantIds(e.id).size;
        collapseHtml = '<button class="entry-collapse-btn" onclick="event.stopPropagation();window._etToggleCollapse(event,\'' + eid + '\')" title="' + (isCollapsed ? '展开 ' + hiddenCount + ' 条回复' : '折叠回复') + '">'
          + (isCollapsed
            ? '<span class="entry-collapsed-hint">' + hiddenCount + '条</span><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>'
            : '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 15 12 9 18 15"/></svg>')
          + '</button>';
      }

      // author display
      let authorHtml = '';
      if (self._mode === 'ai') {
        const authorCls = e.author === 'ai' ? 'ai' : 'human';
        const authorLabel = e.author === 'ai' ? 'AI' : '人';
        const authorIcon = e.author === 'ai'
          ? '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="9" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/><path d="M8 16c1.5 2 5 2 8 0"/></svg>'
          : '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 22c0-4.4 3.6-8 8-8s8 3.6 8 8"/></svg>';
        authorHtml = '<span class="entry-author ' + authorCls + '">' + authorIcon + ' ' + authorLabel + '</span>';
      } else {
        const name = ET_esc(e.author_name || e.author || '用户');
        authorHtml = '<span class="entry-author human">' + name + '</span>';
      }

      // read status (ai mode only)
      let readHtml = '';
      if (self._mode === 'ai') {
        readHtml = e.author === 'human'
          ? (e.ai_status === 'read' ? '<span class="entry-read r-yes">AI已读</span>'
            : '<span class="entry-read r-no">AI未读</span>')
          : (e.read_by_human ? '<span class="entry-read r-yes">人已读</span>' : '<span class="entry-read r-no">人未读</span>');
      }

      // reply info (compact: reference + preview in one row)
      let replyInfoHtml = '';
      if (isReply) {
        let parts = '<span class="entry-reply-to">↳ ' + ET_esc(e.parent_id) + '</span>';
        const parent = self._editEntries.find(p => p.id === e.parent_id);
        if (parent && (parent.content || '').trim()) {
          const preview = (parent.content || '').replace(/\n/g, ' ').slice(0, 40);
          parts += '<span class="entry-reply-preview">' + ET_esc(preview) + (parent.content.length > 40 ? '…' : '') + '</span>';
        }
        replyInfoHtml = '<div class="entry-reply-info">' + parts + '</div>';
      }

      // action buttons
      const canResolve = self._mode === 'ai' || self._userRole === 'super_admin' || self._currentUserGid === self._listOwnerGid;
      const canDelete  = self._mode === 'ai' || self._userRole === 'super_admin' || (e.author_gid && e.author_gid === self._currentUserGid) || e.author === self._currentUserGid;
      let actionsHtml = '';
      // copy button
      if (self._mode === 'ai') {
        actionsHtml += '<button class="entry-act copy" onclick="window._etCopyEntry(event,\'' + eid + '\')" title="复制AI指令">'
          + '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>';
      } else if (self._isCloud) {
        actionsHtml += '<button class="entry-act copy" onclick="window._etCopyLink(event,\'' + eid + '\')" title="复制链接">'
          + '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>';
      }
      // resolve button
      if (canResolve) {
        actionsHtml += '<button class="entry-act resolve" onclick="window._etResolve(event,\'' + eid + '\')" title="完成">'
          + '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg></button>';
      }
      // comment button (always available)
      actionsHtml += '<button class="entry-act comment" onclick="window._etComment(event,\'' + eid + '\')" title="回复">'
        + '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></button>';
      // delete button
      if (canDelete) {
        actionsHtml += '<button class="entry-act delete" onclick="window._etDelete(event,\'' + eid + '\')" title="删除">'
          + '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>';
      }

      const timeStr = ET_bjTime(e.created_at||'');
      // AI entries are readonly (human can't edit AI text)
      const readonly = (self._mode === 'ai' && e.author === 'ai') ? ' readonly style="background:var(--bg2);cursor:default"' : '';

      return '<div class="' + cardCls + '" data-entry-id="' + eid + '" draggable="true"'
        + ' ondragstart="event.dataTransfer.effectAllowed=\'move\';window._etDragStart(event,\'' + eid + '\')"'
        + ' ondragend="window._etDragEnd(event)"'
        + ' ondragover="window._etDragOver(event,\'' + eid + '\')"'
        + ' ondragleave="event.currentTarget.classList.remove(\'drag-over-before\',\'drag-over-after\')"'
        + ' ondrop="event.preventDefault();window._etDrop(event,\'' + eid + '\',event.clientY)">'
        + '<div class="entry-card-head">'
        + collapseHtml
        + '<span class="entry-seq">#' + (hierNum.get(e.id) || (i + 1)) + '</span>'
        + '<span class="entry-id">' + eid + '</span>'
        + authorHtml
        + readHtml
        + '<span class="entry-time">' + ET_esc(timeStr) + '</span>'
        + '<span class="entry-spacer"></span>'
        + '<span class="entry-actions">' + actionsHtml + '</span></div>'
        + replyInfoHtml
        + '<div class="entry-body"><textarea placeholder="输入内容…" oninput="window._etTextChg(event,\'' + eid + '\',this.value)"' + readonly + '>' + ET_esc(e.content||'') + '</textarea></div>'
        + '</div>';
    }).join('');
  }

  /** 新增条目 */
  _addEntry(section, parentId) {
    const now = ET_bjNow();
    const entries = this._editEntries.filter(e => e.section === section);
    const maxSo = entries.reduce((m, e) => Math.max(m, e.sort_order || 0), 0);
    const newEntry = {
      id: EntryThread._genId(),
      parent_id: parentId || null,
      section,
      author: 'human',
      author_name: this._currentUserName || '',
      author_gid: this._currentUserGid || '',
      content: '',
      created_at: now,
      resolved: false,
      sort_order: maxSo + 1,
      read_by_human: true,
      ai_status: this._mode === 'ai' ? 'unread' : '',
    };
    this._editEntries.push(newEntry);
    this._render();
    this._onChange(this._editEntries);
    this._onSave();
    setTimeout(() => {
      const card = this._mountEl.querySelector('.entry-card[data-entry-id="' + newEntry.id + '"]');
      if (card) { card.querySelector('textarea')?.focus(); card.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    }, 50);
  }

  /** 文本变更 */
  _onTextChange(id, value) {
    const e = this._editEntries.find(x => x.id === id);
    if (e) e.content = value;
    this._onChange(this._editEntries);
    this._onSave();
  }

  /** 完成（移入历史）*/
  _resolveEntry(id) {
    const e = this._editEntries.find(x => x.id === id);
    if (!e) return;
    e.resolved = true;
    e.section = 'history';
    e.created_at = (e.created_at || '').replace(' [已解决]', '') + ' [已解决]';
    this._render();
    this._onChange(this._editEntries);
    this._onSave();
  }

  /** 回复 */
  _commentEntry(parentId) {
    const parent = this._editEntries.find(e => e.id === parentId);
    if (!parent) return;
    const section = parent.section;
    const now = ET_bjNow();
    const insertAt = (parent.sort_order || 0) + 1;
    this._editEntries
      .filter(e => e.section === section && (e.sort_order || 0) >= insertAt)
      .forEach(e => { e.sort_order = (e.sort_order || 0) + 1; });
    const newEntry = {
      id: EntryThread._genId(),
      parent_id: parentId,
      section,
      author: 'human',
      author_name: this._currentUserName || '',
      author_gid: this._currentUserGid || '',
      content: '',
      created_at: now,
      resolved: false,
      sort_order: insertAt,
      read_by_human: true,
      ai_status: this._mode === 'ai' ? 'unread' : '',
    };
    this._editEntries.push(newEntry);
    this._render();
    this._onChange(this._editEntries);
    this._onSave();
    setTimeout(() => {
      const card = this._mountEl.querySelector('.entry-card[data-entry-id="' + newEntry.id + '"]');
      if (card) { card.querySelector('textarea')?.focus(); card.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    }, 50);
  }

  /** 删除（级联删除回复）*/
  _deleteEntry(id) {
    const toDelete = new Set([id]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const e of this._editEntries) {
        if (!toDelete.has(e.id) && e.parent_id && toDelete.has(e.parent_id)) {
          toDelete.add(e.id);
          changed = true;
        }
      }
    }
    this._editEntries = this._editEntries.filter(e => !toDelete.has(e.id));
    this._render();
    this._onChange(this._editEntries);
    this._onSave();
  }

  /** 复制 entry AI 指令 */
  _copyEntry(id) {
    const entry = this._editEntries.find(e => e.id === id);
    if (!entry) return;
    // 尝试从 REM 标题栏获取问题编号（解决 _issueId 为空的边界情况）
    let issueId = this._issueId;
    if (!issueId) {
      const headEl = document.querySelector('.rem-head-id');
      if (headEl) issueId = (headEl.textContent || '').replace('#', '').trim();
    }
    const text = '请读dev\\bug_tracker.json的（' + (issueId || '?') + '号）问题卡片中(' + id + ')条目。并执行相应动作，完成之后：\n'
      + '1. 更新 dev\\bug_tracker.json 里该条目的 ai_status 字段\n'
      + '2. 对每条 human 条目分别追加回复卡片（section:"detail", author:"ai", author_name:"Claude", parent_id:该human条目的id），说明该条的处理结果。不要新建主题卡片，只回复已有卡片\n'
      + '注意只改 ai_status，不要把卡片移到历史区\n'
      + '⚠️ JSON 可能被 Electron 自动保存并发写入。写文件前先读盘确认未被外部修改，若内容有变请合并后再写，避免覆盖用户的并发编辑。';
    ET_copyText(text, this._onStatusMsg, '已复制');
  }

  /** 复制 entry 链接（human 模式云端）*/
  _copyLink(id) {
    const entry = this._editEntries.find(e => e.id === id);
    if (!entry) return;
    const text = '条目 #' + this._issueId + ' / ' + id + ' ' + ET_bjTime(entry.created_at||'');
    ET_copyText(text, this._onStatusMsg, '已复制链接');
  }

  // ─── 辅助排序 ─────────────────────────────────────────────────────────────

  _getRootOrder(entry) {
    let current = entry;
    let depth = 0;
    while (current && current.parent_id && depth < 100) {
      const parent = this._editEntries.find(e => e.id === current.parent_id);
      if (!parent) break;
      current = parent;
      depth++;
    }
    return current ? (current.sort_order || 0) : (entry.sort_order || 0);
  }

  _entryDepth(entry) {
    let depth = 0, current = entry, max = 0;
    while (current && current.parent_id && max < 100) {
      const parent = this._editEntries.find(e => e.id === current.parent_id);
      if (!parent) break;
      depth++; current = parent; max++;
    }
    return depth;
  }

  /** 计算层级编号 Map<entryId, "1"|"1.1"|"1.2.1"|...> */
  _computeHierNumbers(entries) {
    const map = new Map();
    const byParent = {}; // parentId|null → children array
    entries.forEach(e => {
      const key = e.parent_id || '__root__';
      if (!byParent[key]) byParent[key] = [];
      byParent[key].push(e);
    });
    const assign = (parentId, prefix) => {
      const children = byParent[parentId || '__root__'];
      if (!children) return;
      // 按当前 sort_order 排序
      children.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
      children.forEach((e, i) => {
        const num = prefix ? prefix + '.' + (i + 1) : String(i + 1);
        map.set(e.id, num);
        assign(e.id, num);
      });
    };
    assign(null, '');
    return map;
  }

  // ─── 折叠/展开 ────────────────────────────────────────────────────────────

  /** 获取直接子条目 */
  _getChildren(parentId) {
    return this._editEntries.filter(e => e.parent_id === parentId);
  }

  /** 递归获取所有子孙条目 ID */
  _getAllDescendantIds(parentId) {
    const ids = new Set();
    const stack = [parentId];
    while (stack.length) {
      const pid = stack.pop();
      this._editEntries.forEach(e => {
        if (e.parent_id === pid && !ids.has(e.id)) {
          ids.add(e.id);
          stack.push(e.id);
        }
      });
    }
    return ids;
  }

  /** 检查 entry 是否有任何被折叠的祖先 */
  _hasCollapsedAncestor(entry) {
    if (!entry.parent_id) return false;
    let current = entry;
    let depth = 0;
    while (current && current.parent_id && depth < 100) {
      if (this._collapsedParents.has(current.parent_id)) return true;
      current = this._editEntries.find(e => e.id === current.parent_id);
      if (!current) break;
      depth++;
    }
    return false;
  }

  /** 切换卡片折叠状态 */
  _toggleCollapse(id) {
    if (this._collapsedParents.has(id)) {
      this._collapsedParents.delete(id);
    } else {
      this._collapsedParents.add(id);
    }
    this._render();
  }

  // ─── 拖拽排序 ────────────────────────────────────────────────────────────

  /** 拖拽开始 */
  _onDragStart(id) {
    this._dragSrcId = id;
    // 如果是主题卡片（有子回复），自动折叠
    const children = this._getChildren(id);
    if (children.length && !this._collapsedParents.has(id)) {
      this._collapsedParents.add(id);
      this._render();
    }
    // 标记被拖拽的卡片
    setTimeout(() => {
      const card = this._mountEl?.querySelector('.entry-card[data-entry-id="' + id + '"]');
      if (card) card.classList.add('dragging');
    }, 0);
  }

  /** 拖拽结束 */
  _onDragEnd() {
    this._dragSrcId = null;
    if (this._mountEl) {
      this._mountEl.querySelectorAll('.entry-card.dragging, .entry-card.drag-over-before, .entry-card.drag-over-after').forEach(el => {
        el.classList.remove('dragging', 'drag-over-before', 'drag-over-after');
      });
    }
  }

  /** 拖拽悬停 */
  _onDragOver(ev, targetId) {
    ev.preventDefault();
    if (!this._dragSrcId || this._dragSrcId === targetId) return;
    const srcEntry = this._editEntries.find(e => e.id === this._dragSrcId);
    const targetEntry = this._editEntries.find(e => e.id === targetId);
    if (!srcEntry || !targetEntry || srcEntry.section !== targetEntry.section) return;
    // 不能拖到自己的子孙上
    const srcDesc = this._getAllDescendantIds(this._dragSrcId);
    if (srcDesc.has(targetId)) return;

    // 显示放置指示线
    const cards = this._mountEl?.querySelectorAll('.entry-card.drag-over-before, .entry-card.drag-over-after');
    cards?.forEach(el => el.classList.remove('drag-over-before', 'drag-over-after'));

    const card = this._mountEl?.querySelector('.entry-card[data-entry-id="' + targetId + '"]');
    if (!card) return;
    const rect = card.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    card.classList.add(ev.clientY < midY ? 'drag-over-before' : 'drag-over-after');
  }

  /** 放置 */
  _onDrop(targetId, clientY) {
    const srcId = this._dragSrcId;
    this._onDragEnd();
    if (!srcId || srcId === targetId) return;

    const srcEntry = this._editEntries.find(e => e.id === srcId);
    const targetEntry = this._editEntries.find(e => e.id === targetId);
    if (!srcEntry || !targetEntry || srcEntry.section !== targetEntry.section) return;

    // 不能拖到自己的子孙上
    const srcDesc = this._getAllDescendantIds(srcId);
    if (srcDesc.has(targetId)) return;

    const section = srcEntry.section;
    const srcBlockIds = new Set([srcId, ...this._getAllDescendantIds(srcId)]);
    // 从 section 条目中移除 src block
    const remaining = this._editEntries
      .filter(e => e.section === section && !srcBlockIds.has(e.id))
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));

    // 找出 target 在 remaining 中的位置
    const targetCard = this._mountEl?.querySelector('.entry-card[data-entry-id="' + targetId + '"]');
    const targetRect = targetCard?.getBoundingClientRect();
    const insertAfter = targetRect ? clientY >= targetRect.top + targetRect.height / 2 : true;
    const targetIdx = remaining.findIndex(e => e.id === targetId);
    if (targetIdx < 0) return;

    // 重新分配 sort_order
    const srcBlock = this._editEntries.filter(e => srcBlockIds.has(e.id));
    let so = 1;
    const insertPos = insertAfter ? targetIdx + 1 : targetIdx;
    for (let i = 0; i < insertPos; i++) {
      remaining[i].sort_order = so++;
    }
    srcBlock.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)).forEach(e => { e.sort_order = so++; });
    for (let i = insertPos; i < remaining.length; i++) {
      remaining[i].sort_order = so++;
    }

    this._render();
    this._onChange(this._editEntries);
    this._onSave();
  }

  // ─── 全局事件桥接 ──────────────────────────────────────────────────────────
  // EntryThread 实例注册到 window 以便 onclick 内联回调找到

  static _instances = new Map();

  /** 绑定实例到 mountEl 的 id */
  _bindGlobal(id) {
    if (!this._mountEl) return;
    if (!this._mountEl.id) this._mountEl.id = 'et_' + EntryThread._genId();
    EntryThread._instances.set(this._mountEl.id, this);
  }

  static _find(el) {
    let cur = el;
    while (cur) {
      if (cur.id && EntryThread._instances.has(cur.id)) return EntryThread._instances.get(cur.id);
      cur = cur.parentElement;
    }
    return null;
  }

  static _genId() { return 'e_' + Math.random().toString(36).slice(2, 10); }
}

// ─── 静态工具函数 ─────────────────────────────────────────────────────────

function ET_esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
}

function ET_bjTime(utcStr) {
  if (utcStr == null || utcStr === '') return '';
  utcStr = String(utcStr);
  const resolvedSuffix = utcStr.includes('[已解决]') ? ' [已解决]' : '';
  const clean = utcStr.replace(' [已解决]', '').trim();
  if (!clean.includes('T') && !clean.includes('Z')) {
    return clean.slice(0, 16) + resolvedSuffix;
  }
  try {
    const d = new Date(clean);
    if (isNaN(d.getTime())) return (utcStr||'').slice(0, 16) + resolvedSuffix;
    const bj = new Date(d.getTime() + 8 * 3600000);
    return bj.toISOString().replace('T', ' ').slice(0, 16) + resolvedSuffix;
  } catch { return (utcStr||'').slice(0, 16) + resolvedSuffix; }
}

function ET_bjNow() {
  const d = new Date();
  const bj = new Date(d.getTime() + 8 * 3600000);
  return bj.toISOString().replace('T', ' ').slice(0, 16);
}

function ET_copyText(text, statusCb, label) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      if (statusCb) statusCb(label || '已复制');
    }).catch(() => {});
  }
}

// ─── 全局 onclick 处理函数 ──────────────────────────────────────────────────
// 由 entry_thread.js 全局注册，供 HTML 内联 onclick 调用
window._etAdd = function(ev, section, parentId) {
  const t = EntryThread._find(ev.target);
  if (t) t._addEntry(section, parentId || null);
};
window._etComment = function(ev, parentId) {
  const t = EntryThread._find(ev.target);
  if (t) t._commentEntry(parentId);
};
window._etResolve = function(ev, id) {
  const t = EntryThread._find(ev.target);
  if (t) t._resolveEntry(id);
};
window._etDelete = function(ev, id) {
  const t = EntryThread._find(ev.target);
  if (t) t._deleteEntry(id);
};
window._etTextChg = function(ev, id, val) {
  const t = EntryThread._find(ev.target);
  if (t) t._onTextChange(id, val);
};
window._etCopyEntry = function(ev, id) {
  const t = EntryThread._find(ev.target);
  if (t) t._copyEntry(id);
};
window._etCopyLink = function(ev, id) {
  const t = EntryThread._find(ev.target);
  if (t) t._copyLink(id);
};
window._etToggleCollapse = function(ev, id) {
  const t = EntryThread._find(ev.target);
  if (t) t._toggleCollapse(id);
};
window._etDragStart = function(ev, id) {
  const t = EntryThread._find(ev.target);
  if (t) t._onDragStart(id);
};
window._etDragEnd = function(ev) {
  const t = EntryThread._find(ev.target);
  if (t) t._onDragEnd();
};
window._etDragOver = function(ev, id) {
  const t = EntryThread._find(ev.target);
  if (t) t._onDragOver(ev, id);
};
window._etDrop = function(ev, id, clientY) {
  ev.preventDefault();
  const t = EntryThread._find(ev.target);
  if (t) t._onDrop(id, clientY);
};

