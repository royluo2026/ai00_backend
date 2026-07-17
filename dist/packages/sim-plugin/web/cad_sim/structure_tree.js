/**
 * AssemblyTree — 装配体结构树组件
 * 渲染 JT 装配体结构树，支持折叠/展开和节点选择
 */
class AssemblyTree {
  // node_type → 图标颜色（Catppuccin 色板）
  static NODE_TYPE_COLORS = {
    line_process:     '#cba6f7',
    station_process:  '#89b4fa',
    process:          '#74c7ec',
    operation:        '#a6e3a1',
    part:             '#f9e2af',
    non_standard_part:'#f9e2af',
    standard_part:    '#f9e2af',
    support_material: '#fab387',
  };

  constructor(containerEl, onNodeSelect) {
    this._container = containerEl;
    this._onNodeSelect = onNodeSelect || (() => {});
    this._selectedPath = null;
    this._expandedPaths = new Set();
    this._tree = null;
    this._nodeTypeColors = false;
  }

  setTree(treeJson) {
    this._tree = Array.isArray(treeJson) ? treeJson : (treeJson ? [treeJson] : []);
    this._render();
  }

  setNodeTypeColors(enable) {
    this._nodeTypeColors = !!enable;
    if (this._tree) this._render();
  }

  clear() {
    this._tree = null;
    this._selectedPath = null;
    this._expandedPaths.clear();
    this._container.innerHTML = '';
  }

  highlightNode(nodePath) {
    this._selectedPath = nodePath;
    this._container.querySelectorAll('.at-node').forEach(el => {
      el.classList.toggle('at-selected', el.dataset.path === nodePath);
    });
  }

  getSelectedNodePath() {
    return this._selectedPath;
  }

  getMultiSelectedPaths() {
    return Array.from(this._container.querySelectorAll('.at-node.at-checked'))
      .map(el => el.dataset.path);
  }

  _render() {
    this._container.innerHTML = '';
    if (!this._tree || !this._tree.length) {
      this._container.innerHTML = '<div class="at-empty">暂无结构树数据</div>';
      return;
    }
    const ul = document.createElement('ul');
    ul.className = 'at-root';
    for (const node of this._tree) {
      ul.appendChild(this._buildNodeEl(node));
    }
    this._container.appendChild(ul);
    this._bindEvents();
  }

  _buildNodeEl(node) {
    const li = document.createElement('li');
    li.className = 'at-item';

    const row = document.createElement('div');
    row.className = 'at-node';
    row.dataset.path = node.path;
    if (node.node_type) row.dataset.nodeType = node.node_type;
    if (node.path === this._selectedPath) row.classList.add('at-selected');

    // 展开/折叠箭头
    const arrow = document.createElement('span');
    arrow.className = 'at-arrow';
    if (!node.is_leaf && node.children && node.children.length > 0) {
      const isExpanded = this._expandedPaths.has(node.path);
      arrow.innerHTML = isExpanded ? this._iconChevronDown() : this._iconChevronRight();
      arrow.dataset.expandable = '1';
    } else {
      arrow.innerHTML = '<span class="at-arrow-placeholder"></span>';
    }

    // 复选框（多选干涉检测用）
    const cb = document.createElement('span');
    cb.className = 'at-check';
    cb.innerHTML = this._iconCheck();
    cb.title = '选择用于干涉检测';

    // 图标
    const icon = document.createElement('span');
    icon.className = 'at-icon';
    icon.innerHTML = node.is_leaf ? this._iconPart() : this._iconAssembly();
    if (this._nodeTypeColors && node.node_type) {
      const color = AssemblyTree.NODE_TYPE_COLORS[node.node_type];
      if (color) icon.style.color = color;
    }

    // 名称
    const label = document.createElement('span');
    label.className = 'at-label';
    label.textContent = node.name;

    row.appendChild(arrow);
    row.appendChild(cb);
    row.appendChild(icon);
    row.appendChild(label);
    li.appendChild(row);

    // 子节点
    if (!node.is_leaf && node.children && node.children.length > 0) {
      const childUl = document.createElement('ul');
      childUl.className = 'at-children';
      if (!this._expandedPaths.has(node.path)) {
        childUl.style.display = 'none';
      }
      for (const child of node.children) {
        childUl.appendChild(this._buildNodeEl(child));
      }
      li.appendChild(childUl);
    }

    return li;
  }

  _bindEvents() {
    this._container.addEventListener('click', e => {
      const arrowEl = e.target.closest('.at-arrow[data-expandable]');
      if (arrowEl) {
        const row = arrowEl.closest('.at-node');
        const li = row.parentElement;
        const path = row.dataset.path;
        const childUl = li.querySelector(':scope > .at-children');
        if (childUl) {
          const isHidden = childUl.style.display === 'none';
          childUl.style.display = isHidden ? '' : 'none';
          if (isHidden) {
            this._expandedPaths.add(path);
            arrowEl.innerHTML = this._iconChevronDown();
          } else {
            this._expandedPaths.delete(path);
            arrowEl.innerHTML = this._iconChevronRight();
          }
        }
        return;
      }
      const checkEl = e.target.closest('.at-check');
      if (checkEl) {
        const row = checkEl.closest('.at-node');
        row.classList.toggle('at-checked');
        return;
      }
      const nodeEl = e.target.closest('.at-node');
      if (nodeEl) {
        this._selectedPath = nodeEl.dataset.path;
        this._container.querySelectorAll('.at-node').forEach(el => {
          el.classList.toggle('at-selected', el.dataset.path === this._selectedPath);
        });
        this._onNodeSelect(this._selectedPath);
      }
    });
  }

  // ── SVG 图标 ──
  _iconChevronRight() {
    return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`;
  }
  _iconChevronDown() {
    return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>`;
  }
  _iconAssembly() {
    return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`;
  }
  _iconPart() {
    return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>`;
  }
  _iconCheck() {
    return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
  }
}

window.AssemblyTree = AssemblyTree;
