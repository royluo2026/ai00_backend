'use strict';

/**
 * TreeView — 树形视图组件
 *
 * 将扁平行数组按 parentField 字段组织为树形，
 * 第一列带缩进 + 展开/折叠，其余列正常渲染。
 *
 * 用法：
 *   const tv = new TreeView({
 *     containerEl:  el,
 *     columns:      visibleCols,
 *     cellRenderer: { title: (v, row) => '<b>' + v + '</b>' },
 *     onRowClick:   (row) => rdp.open(row),
 *     rowClass:     (row) => row._source === 'cloud' ? 'ge-row-cloud' : '',
 *   });
 *   tv.setRows(rows, 'parent_gid');
 */
class TreeView {
  constructor({ containerEl, columns, cellRenderer, onRowClick, rowClass } = {}) {
    this._el           = containerEl;
    this._columns      = columns      || [];
    this._cellRenderer = cellRenderer || {};
    this._onRowClick   = onRowClick   || null;
    this._rowClass     = rowClass     || null;
    this._expanded     = new Set();   // expanded gids
    this._allRows      = [];
    this._parentField  = 'parent_gid';
  }

  // ─── Public API ──────────────────────────────────────────────

  setColumns(cols) {
    this._columns = cols || [];
    this._render();
  }

  setRows(rows, parentField) {
    this._allRows     = rows || [];
    this._parentField = parentField || 'parent_gid';
    this._render();
  }

  /** 展开全部节点 */
  expandAll() {
    this._allRows.forEach(r => { if (r.gid) this._expanded.add(r.gid); });
    this._render();
  }

  /** 折叠全部节点 */
  collapseAll() {
    this._expanded.clear();
    this._render();
  }

  // ─── Tree Build ──────────────────────────────────────────────

  _buildTree() {
    const rows        = this._allRows;
    const parentField = this._parentField;
    const byGid       = new Map(rows.filter(r => r.gid).map(r => [r.gid, r]));
    const childMap    = new Map();   // parentGid → [row]

    rows.forEach(r => {
      const pid = r[parentField];
      const key = (pid && byGid.has(pid)) ? pid : null;
      if (!childMap.has(key)) childMap.set(key, []);
      childMap.get(key).push(r);
    });

    const flat = [];
    const walk = (parentGid, depth) => {
      const kids = childMap.get(parentGid) || [];
      kids.forEach(row => {
        const hasKids = (childMap.get(row.gid) || []).length > 0;
        flat.push({ ...row, _depth: depth, _hasKids: hasKids });
        if (hasKids && this._expanded.has(row.gid)) {
          walk(row.gid, depth + 1);
        }
      });
    };
    walk(null, 0);
    return flat;
  }

  // ─── Render ──────────────────────────────────────────────────

  _render() {
    if (!this._el) return;
    const visCols  = this._columns.filter(c => c.visible !== false);
    const treeRows = this._buildTree();
    const firstCol = visCols[0];
    const restCols = visCols.slice(1);

    // ── Header ──
    let head = '<div class="tv-header">';
    head += `<div class="tv-tree-head">${firstCol ? _tvHe(firstCol.label) : '名称'}</div>`;
    restCols.forEach(c => {
      head += `<div class="tv-col-head" style="width:${c.width || 100}px">${_tvHe(c.label)}</div>`;
    });
    head += '</div>';

    // ── Body rows ──
    let body = '<div class="tv-body">';
    treeRows.forEach(row => {
      if (row._isGroupHeader) return;
      const indent     = row._depth * 20;
      const expanded   = this._expanded.has(row.gid);
      const extraClass = this._rowClass ? this._rowClass(row) : '';

      body += `<div class="tv-row ${extraClass}" data-gid="${_tvHe(row.gid || '')}">`;

      // Tree cell
      const fVal     = firstCol ? (row[firstCol.key] ?? '') : (row.title || row.name || '');
      const fRendered = (firstCol && this._cellRenderer[firstCol.key])
        ? this._cellRenderer[firstCol.key](row[firstCol.key], row)
        : _tvHe(String(fVal));

      body += `<div class="tv-tree-cell" style="padding-left:${6 + indent}px">`;
      if (row._hasKids) {
        body += `<span class="tv-toggle${expanded ? ' open' : ''}" data-gid="${_tvHe(row.gid)}">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </span>`;
      } else {
        body += '<span class="tv-no-toggle"></span>';
      }
      body += `<span class="tv-cell-label">${fRendered}</span>`;
      body += '</div>';

      // Rest of columns
      restCols.forEach(c => {
        const val      = row[c.key];
        const rendered = this._cellRenderer[c.key]
          ? this._cellRenderer[c.key](val, row)
          : _tvHe(String(val ?? ''));
        body += `<div class="tv-cell" style="width:${c.width || 100}px">${rendered}</div>`;
      });

      body += '</div>';
    });
    body += '</div>';

    this._el.innerHTML = `<div class="tv-root">${head}${body}</div>`;
    this._bindEvents();
  }

  _bindEvents() {
    // Expand/collapse
    this._el.querySelectorAll('.tv-toggle').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const gid = btn.dataset.gid;
        if (this._expanded.has(gid)) this._expanded.delete(gid);
        else                          this._expanded.add(gid);
        this._render();
      });
    });

    // Row click
    this._el.querySelectorAll('.tv-row').forEach(rowEl => {
      rowEl.addEventListener('click', () => {
        // Highlight active
        this._el.querySelectorAll('.tv-row.tv-active').forEach(r => r.classList.remove('tv-active'));
        rowEl.classList.add('tv-active');
        const gid    = rowEl.dataset.gid;
        const rowData = this._allRows.find(r => r.gid === gid);
        if (rowData && this._onRowClick) this._onRowClick(rowData);
      });
    });
  }
}

// HTML escape (private to this module to avoid collision)
function _tvHe(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
}

