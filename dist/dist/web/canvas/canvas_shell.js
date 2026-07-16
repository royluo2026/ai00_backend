'use strict';
/**
 * CanvasShell — 统一画布壳
 *
 * 职责：
 *   - 四栏布局（工具栏 / 左面板 / 视口 / 右面板 / 底部详情）
 *   - GridSystem 在视口内的 Pan/Zoom（wheel + 中键/Space 拖拽）
 *   - 卡片增删、定位（含 zoom 补偿）、对齐参考线
 *   - 协调：ConnectionLayer / LayerManager / CanvasSearch / TemplateLibrary
 *   - 画布数据序列化/持久化（localStorage，bridge 后续接入）
 *   - 画布类型插件注册（window.CANVAS_TYPES）
 *
 * URL 参数：
 *   canvas_type  画布类型（对应 window.CANVAS_TYPES 的 key）
 *   canvas_gid   画布 GID（用于 localStorage key / bridge 查询）
 *   canvas_name  画布名称（可选，用于创建时的默认名称）
 */

// ── 常量 ──────────────────────────────────────────────────────────────────────
const _GS_DEFAULTS = {
  cols: 24, rowHeight: 80, gap: 12,
  overlayOpacity: 0.35, overlayColor: '#888888',
};
const _GS_LS_KEY = 'cs:grid-config';
const _ZOOM_MIN  = 0.2;
const _ZOOM_MAX  = 2.5;
const _ZOOM_STEP = 1.18;

// ── 内部工具 ──────────────────────────────────────────────────────────────────
function _uuid() {
  return `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}
function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── CanvasShell ───────────────────────────────────────────────────────────────
class CanvasShell {
  constructor() {
    const params         = new URLSearchParams(location.search);
    this._canvasGid      = params.get('canvas_gid')  || 'demo';
    this._canvasType     = params.get('canvas_type') || 'generic';
    this._canvasName     = params.get('canvas_name') || '未命名画布';

    // Pan/Zoom 状态
    this._zoom = 1;
    this._panX = 40;
    this._panY = 40;

    // 卡片数据
    this._cards      = new Map();     // id → cardDef
    this._cardFrames = new Map();     // id → CardFrame
    this._layerMap   = new Map();     // cardId → {cf, layer_id}

    // 编辑模式
    this._editMode    = false;
    this._dirty       = false;
    this._spaceDown   = false;

    // 拖拽状态
    this._guideOverlay = null;

    // 子模块
    this._gridSystem   = null;
    this._connection   = null;
    this._layers       = null;
    this._search       = null;
    this._templates    = null;

    // 插件
    this._plugin = null;
  }

  // ── 初始化 ────────────────────────────────────────────────────────────────
  async init() {
    this._applyTheme();
    this._bindThemeMessage();

    // 加载画布数据
    const canvasDef = this._loadCanvas();

    // 初始化 GridSystem
    const gridHost = document.getElementById('csGridHost');
    const gsConfig = this._loadGridConfig();
    this._gridSystem = new GridSystem(gridHost, {
      ...gsConfig,
      overlayVisible: false,
    });

    // 注入 SVG 叠层到 csWorld（GridSystem 已挂 .gs-container 到 gridHost）
    const world = document.getElementById('csWorld');
    const connSvg  = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    connSvg.className = 'cs-connection-svg';
    connSvg.id = 'csConnectionSvg';
    world.appendChild(connSvg);

    const guideSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    guideSvg.className = 'cs-guide-svg';
    guideSvg.id = 'csGuideSvg';
    guideSvg.setAttribute('overflow', 'visible');
    world.appendChild(guideSvg);
    this._guideOverlay = guideSvg;

    // 初始化子模块
    this._connection = new ConnectionLayer(
      connSvg, gridHost, () => this._zoom,
    );
    this._layers = new LayerManager(
      canvasDef.layers || [],
      () => this._onLayerChange(),
    );
    this._search    = new CanvasSearch(this);
    this._templates = new TemplateLibrary(this);

    // 加载模板
    this._templates.load(this._canvasType);

    // 动态加载画布类型脚本（404 时静默继续）
    await this._loadTypeScript(`types/${this._canvasType}_type.js`);

    // 加载画布类型插件
    this._plugin = window.CANVAS_TYPES?.[this._canvasType] || null;

    // 绑定事件
    this._bindToolbar();
    this._bindViewportEvents();
    this._bindKeyboard();
    this._bindDropZone();

    // 更新名称
    document.title = canvasDef.name || this._canvasName;
    const nameEl = document.getElementById('csCanvasName');
    if (nameEl) nameEl.textContent = canvasDef.name || this._canvasName;

    // 渲染连线（先反序列化）
    this._connection.deserialize(canvasDef.connections || []);

    // 渲染卡片
    (canvasDef.cards || []).forEach(card => this._renderCard(card));

    // 刷新连线位置
    this._connection.refresh(this._cardFrames);

    // 渲染左侧调色板
    this._renderPalette();

    // 渲染右侧模板列表
    this._templates.renderPanel(document.getElementById('csTemplateList'));

    // 渲染图层面板
    this._layers.renderPanel(document.getElementById('csLayerList'));

    // 渲染搜索框
    this._search.renderSearchBar(document.getElementById('csSearchBar'));

    // 渲染插件工具栏操作
    this._renderTypeActions();

    // 渲染 mode bar（初始为使用模式）
    this._renderModeBar();

    // 初始 transform
    this._setTransform();

    // 类型插件 onInit 钩子（载入画布数据 + 渲染节点）
    if (this._plugin?.onInit) await this._plugin.onInit(this);

    // 空状态检查
    this._checkEmpty();
  }

  // ── 主题 ──────────────────────────────────────────────────────────────────
  _applyTheme(theme) {
    const t = theme || localStorage.getItem('system.theme') || 'light';
    document.documentElement.setAttribute('data-theme', t);
  }
  _bindThemeMessage() {
    window.addEventListener('message', e => {
      if (e.data?.type === 'theme') this._applyTheme(e.data.theme);
    });
  }

  // ── GridSystem 配置持久化 ──────────────────────────────────────────────────
  _loadGridConfig() {
    try {
      const s = localStorage.getItem(_GS_LS_KEY);
      return s ? { ..._GS_DEFAULTS, ...JSON.parse(s) } : { ..._GS_DEFAULTS };
    } catch { return { ..._GS_DEFAULTS }; }
  }
  _saveGridConfig(cfg) {
    localStorage.setItem(_GS_LS_KEY, JSON.stringify(cfg));
  }

  // ── 画布数据持久化（localStorage，后续换 bridge）─────────────────────────
  _canvasKey() { return `cs:canvas:${this._canvasGid}`; }

  _loadCanvas() {
    try {
      const s = localStorage.getItem(this._canvasKey());
      if (s) return JSON.parse(s);
    } catch {}
    return {
      gid: this._canvasGid,
      name: this._canvasName,
      canvas_type: this._canvasType,
      grid_config: { ..._GS_DEFAULTS },
      cards: [],
      connections: [],
      layers: [],
    };
  }

  save() {
    if (this._plugin?.onSave) return this._plugin.onSave(this);
    const def = {
      gid:         this._canvasGid,
      name:        document.getElementById('csCanvasName')?.textContent || this._canvasName,
      canvas_type: this._canvasType,
      grid_config: this._gridSystem?.toConfig() || {},
      cards:       this._serializeCards(),
      connections: this._connection?.serialize() || [],
      layers:      this._layers?.serialize() || [],
    };
    localStorage.setItem(this._canvasKey(), JSON.stringify(def));
    this._dirty = false;
    document.getElementById('csUnsavedDot')?.classList.add('hidden');
    return def;
  }

  _markDirty() {
    this._dirty = true;
    document.getElementById('csUnsavedDot')?.classList.remove('hidden');
  }

  _serializeCards() {
    const cards = [];
    this._cards.forEach(card => {
      const cf  = this._cardFrames.get(card.id);
      const cfg = cf?.toConfig() || {};
      cards.push({
        ...card,
        col_start: cfg.col_start ?? card.col_start,
        row_start: cfg.row_start ?? card.row_start,
        col_span:  cfg.col_span  ?? card.col_span,
        row_span:  cfg.row_span  ?? card.row_span,
      });
    });
    return cards;
  }

  // ── 动态脚本加载 ──────────────────────────────────────────────────────────
  _loadTypeScript(src) {
    return new Promise(resolve => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = resolve;  // 404 时静默继续（generic 类型无附属脚本）
      document.head.appendChild(s);
    });
  }

  // ── Pan/Zoom ───────────────────────────────────────────────────────────────
  _setTransform() {
    const world = document.getElementById('csWorld');
    if (world) {
      world.style.transform = `translate(${this._panX}px,${this._panY}px) scale(${this._zoom})`;
    }
    const zoomLabel = document.getElementById('csZoomLabel');
    if (zoomLabel) zoomLabel.textContent = Math.round(this._zoom * 100) + '%';
  }

  _zoomAt(factor, vpX, vpY) {
    const newZoom = Math.max(_ZOOM_MIN, Math.min(_ZOOM_MAX, this._zoom * factor));
    if (newZoom === this._zoom) return;
    // 锚定视口坐标 (vpX, vpY) 对应的世界坐标不变
    const worldX = (vpX - this._panX) / this._zoom;
    const worldY = (vpY - this._panY) / this._zoom;
    this._zoom = newZoom;
    this._panX = vpX - worldX * newZoom;
    this._panY = vpY - worldY * newZoom;
    this._setTransform();
  }

  _fitToScreen() {
    if (!this._cards.size) { this._zoom = 1; this._panX = 40; this._panY = 40; this._setTransform(); return; }

    const gs = this._gridSystem;
    if (!gs) return;
    let minX = Infinity, minY = Infinity, maxX = 0, maxY = 0;

    this._cards.forEach(card => {
      const r = gs.cellPixelRect(
        card.col_start || 1, card.row_start || 1,
        card.col_span  || 3, card.row_span  || 3,
      );
      minX = Math.min(minX, r.x);
      minY = Math.min(minY, r.y);
      maxX = Math.max(maxX, r.x + r.w);
      maxY = Math.max(maxY, r.y + r.h);
    });

    const PAD = 60;
    const vp  = document.getElementById('csViewport');
    if (!vp) return;
    const vpW = vp.clientWidth;
    const vpH = vp.clientHeight;
    const contentW = maxX - minX + PAD * 2;
    const contentH = maxY - minY + PAD * 2;

    this._zoom = Math.max(_ZOOM_MIN, Math.min(_ZOOM_MAX, Math.min(vpW / contentW, vpH / contentH)));
    this._panX = (vpW - contentW * this._zoom) / 2 - (minX - PAD) * this._zoom;
    this._panY = (vpH - contentH * this._zoom) / 2 - (minY - PAD) * this._zoom;
    this._setTransform();
  }

  _screenToWorld(clientX, clientY) {
    const vr = document.getElementById('csViewport').getBoundingClientRect();
    return {
      x: (clientX - vr.left - this._panX) / this._zoom,
      y: (clientY - vr.top  - this._panY) / this._zoom,
    };
  }

  _worldToGridCell(worldX, worldY) {
    const gs = this._gridSystem;
    if (!gs) return { col: 1, row: 1 };
    const { cols, rowHeight, gap } = gs._opts;
    const colW = gs._colWidth || 80;
    const col  = Math.max(1, Math.min(cols, Math.floor(Math.max(0, worldX) / (colW + gap)) + 1));
    const row  = Math.max(1, Math.floor(Math.max(0, worldY) / (rowHeight + gap)) + 1);
    return { col, row };
  }

  /** 返回视口中央对应的 grid cell（用于双击模板默认位置）*/
  _viewportCenterCell() {
    const vp  = document.getElementById('csViewport');
    if (!vp) return { col: 3, row: 3 };
    const vpW = vp.clientWidth;
    const vpH = vp.clientHeight;
    const w   = this._screenToWorld(vp.getBoundingClientRect().left + vpW / 2,
                                     vp.getBoundingClientRect().top  + vpH / 2);
    return this._worldToGridCell(w.x, w.y);
  }

  // ── 视口事件绑定 ──────────────────────────────────────────────────────────
  _bindViewportEvents() {
    const vp = document.getElementById('csViewport');
    if (!vp) return;

    // 滚轮缩放
    vp.addEventListener('wheel', e => {
      e.preventDefault();
      const rect = vp.getBoundingClientRect();
      const vpX  = e.clientX - rect.left;
      const vpY  = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? _ZOOM_STEP : 1 / _ZOOM_STEP;
      this._zoomAt(factor, vpX, vpY);
    }, { passive: false });

    // 中键/Space+左键 平移
    let panning  = false;
    let panStartX = 0, panStartY = 0;
    let panStartPanX = 0, panStartPanY = 0;

    const startPan = (e) => {
      panning = true;
      panStartX = e.clientX;
      panStartY = e.clientY;
      panStartPanX = this._panX;
      panStartPanY = this._panY;
      vp.classList.add('cs-panning');
    };
    const stopPan = () => {
      panning = false;
      vp.classList.remove('cs-panning');
    };

    vp.addEventListener('mousedown', e => {
      if (e.button === 1 || (e.button === 0 && this._spaceDown)) {
        e.preventDefault();
        startPan(e);
      }
    });

    window.addEventListener('mousemove', e => {
      if (!panning) return;
      this._panX = panStartPanX + (e.clientX - panStartX);
      this._panY = panStartPanY + (e.clientY - panStartY);
      this._setTransform();
    });

    window.addEventListener('mouseup', e => {
      if (e.button === 1 || e.button === 0) stopPan();
    });

    // 在视口上拖放（从模板库拖入）
    vp.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
    vp.addEventListener('drop', e => {
      e.preventDefault();
      const tplId = e.dataTransfer.getData('text/plain');
      if (!tplId || !this._templates) return;
      const def = this._templates.instantiate(tplId);
      if (!def) return;
      const world = this._screenToWorld(e.clientX, e.clientY);
      const { col, row } = this._worldToGridCell(world.x, world.y);
      this.addCard(def, col, row);
    });
  }

  // ── 键盘快捷键 ────────────────────────────────────────────────────────────
  _bindKeyboard() {
    document.addEventListener('keydown', e => {
      if (e.key === ' ' && !['INPUT','TEXTAREA'].includes(e.target.tagName)) {
        e.preventDefault();
        this._spaceDown = true;
      }
      if (e.key === 'Escape') {
        this._closeBottomPanel();
        this._connection?.deselectAll();
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (this._editMode && this._selectedCardId) {
          this._confirmDeleteCard(this._selectedCardId);
        }
        if (this._editMode) {
          this._connection?.deleteSelected();
          this._markDirty();
        }
      }
      if (e.ctrlKey && e.key === 's') { e.preventDefault(); this.save(); }
    });
    document.addEventListener('keyup', e => {
      if (e.key === ' ') this._spaceDown = false;
    });
  }

  // ── Drop zone（从调色板拖入）─────────────────────────────────────────────
  _bindDropZone() {
    const gridHost = document.getElementById('csGridHost');
    if (!gridHost) return;
    gridHost.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
    gridHost.addEventListener('drop', e => {
      e.preventDefault();
      const tplId    = e.dataTransfer.getData('text/plain');
      const typeKey  = e.dataTransfer.getData('cs/palette-type');

      const world = this._screenToWorld(e.clientX, e.clientY);
      const { col, row } = this._worldToGridCell(world.x, world.y);

      if (typeKey && this._plugin?.cardTypes?.[typeKey]) {
        const cardType = this._plugin.cardTypes[typeKey];
        this.addCard({
          type:     typeKey,
          label:    cardType.label || typeKey,
          col_span: cardType.defaultColSpan || 3,
          row_span: cardType.defaultRowSpan || 3,
          config:   {},
        }, col, row);
      } else if (tplId && this._templates) {
        const def = this._templates.instantiate(tplId);
        if (def) this.addCard(def, col, row);
      }
    });
  }

  // ── 工具栏绑定 ────────────────────────────────────────────────────────────
  _bindToolbar() {
    document.getElementById('csToggleLeft')      ?.addEventListener('click', () => this._togglePanel('left'));
    document.getElementById('csToggleRight')     ?.addEventListener('click', () => this._togglePanel('right'));
    document.getElementById('csZoomIn')          ?.addEventListener('click', () => this._zoomCenter(_ZOOM_STEP));
    document.getElementById('csZoomOut')         ?.addEventListener('click', () => this._zoomCenter(1 / _ZOOM_STEP));
    document.getElementById('csZoomFit')         ?.addEventListener('click', () => this._fitToScreen());
    document.getElementById('csZoomLabel')       ?.addEventListener('click', () => { this._zoom = 1; this._panX = 40; this._panY = 40; this._setTransform(); });
    document.getElementById('csLayerBtn')        ?.addEventListener('click', e => this._toggleLayerPanel(e.currentTarget));
    document.getElementById('csGridSettingsBtn') ?.addEventListener('click', e => this._toggleGsPanel(e.currentTarget));

    // 网格设置面板
    document.getElementById('csGsPanelClose')    ?.addEventListener('click', () => document.getElementById('csGsPanel')?.classList.add('hidden'));
    document.getElementById('csGsPanelApply')    ?.addEventListener('click', () => this._applyGridSettings());
    document.getElementById('csGsOpacity')       ?.addEventListener('input', e => {
      const val = document.getElementById('csGsOpacityVal');
      if (val) val.textContent = Math.round(e.target.value * 100) + '%';
    });

    // 图层面板 - 新增按钮
    document.getElementById('csLayerAddBtn') ?.addEventListener('click', async () => {
      const name = await this._promptText('新建图层', '图层名称', '新图层');
      if (name) {
        this._layers.addLayer(name);
        this._layers.renderPanel(document.getElementById('csLayerList'));
        this._markDirty();
      }
    });

    // 底部面板关闭
    document.getElementById('csBottomClose') ?.addEventListener('click', () => this._closeBottomPanel());

    // Modal 关闭
    document.getElementById('csInputModalClose')  ?.addEventListener('click', () => this._resolveInputModal(null));
    document.getElementById('csInputModalCancel') ?.addEventListener('click', () => this._resolveInputModal(null));
    document.getElementById('csInputModalOk')     ?.addEventListener('click', () => {
      const v = document.getElementById('csInputModalField')?.value.trim() || null;
      this._resolveInputModal(v);
    });
    document.getElementById('csInputModalField')  ?.addEventListener('keydown', e => {
      if (e.key === 'Enter')  this._resolveInputModal(document.getElementById('csInputModalField').value.trim() || null);
      if (e.key === 'Escape') this._resolveInputModal(null);
    });
    document.getElementById('csConfirmModalCancel')?.addEventListener('click', () => this._resolveConfirmModal(false));
    document.getElementById('csConfirmModalOk')    ?.addEventListener('click', () => this._resolveConfirmModal(true));
  }

  _zoomCenter(factor) {
    const vp = document.getElementById('csViewport');
    if (!vp) return;
    this._zoomAt(factor, vp.clientWidth / 2, vp.clientHeight / 2);
  }

  // ── 模式栏渲染 ─────────────────────────────────────────────────────────────
  _renderModeBar() {
    const bar = document.getElementById('csModeBar');
    if (!bar) return;
    if (this._editMode) {
      bar.innerHTML = `
        <div class="cs-mode-bar">
          <span class="cs-mode-hint">编辑模式 — 拖拽移位，右下角调整大小</span>
          <button class="cs-btn-ghost cs-tb-btn" id="csBtnAddCard">
            <svg class="icon" width="12" height="12"><use href="#icon-plus"/></svg>
            添加卡片
          </button>
          <button class="cs-btn-ghost cs-tb-btn" id="csBtnCancelEdit">取消</button>
          <button class="cs-btn-accent cs-tb-btn" id="csBtnSaveEdit">保存</button>
        </div>`;
      document.getElementById('csBtnAddCard')    ?.addEventListener('click', () => this._addDefaultCard());
      document.getElementById('csBtnCancelEdit') ?.addEventListener('click', () => this._exitEditMode(false));
      document.getElementById('csBtnSaveEdit')   ?.addEventListener('click', () => this._exitEditMode(true));
    } else {
      bar.innerHTML = `
        <button class="cs-tb-btn" id="csBtnEnterEdit">
          <svg class="icon" width="12" height="12"><use href="#icon-note"/></svg>
          编辑
        </button>`;
      document.getElementById('csBtnEnterEdit')?.addEventListener('click', () => this._enterEditMode());
    }
  }

  // ── 编辑模式 ──────────────────────────────────────────────────────────────
  _enterEditMode() {
    this._editMode = true;
    this._gridSystem?.setOverlayVisible(true);
    this._cardFrames.forEach(cf => cf.setEditMode(true));
    this._renderModeBar();
  }

  _exitEditMode(save) {
    this._editMode = false;
    this._gridSystem?.setOverlayVisible(false);
    this._cardFrames.forEach(cf => cf.setEditMode(false));
    if (save) this.save();
    else { document.getElementById('csUnsavedDot')?.classList.add('hidden'); this._dirty = false; }
    this._renderModeBar();
  }

  // ── 调色板渲染 ────────────────────────────────────────────────────────────
  _renderPalette() {
    const paletteEl = document.getElementById('csPalette');
    if (!paletteEl) return;

    if (this._plugin?.renderPalette) {
      paletteEl.innerHTML = '';
      this._plugin.renderPalette(paletteEl);
      return;
    }

    // 通用默认调色板
    paletteEl.innerHTML = `
      <div class="cs-palette-section-title">通用</div>
      <div class="cs-palette-item" draggable="true" data-type="note">
        <svg class="icon" width="14" height="14"><use href="#icon-note"/></svg>
        备注卡片
      </div>
      <div class="cs-palette-item" draggable="true" data-type="module">
        <svg class="icon" width="14" height="14"><use href="#icon-table"/></svg>
        模块卡片
      </div>
    `;

    paletteEl.querySelectorAll('.cs-palette-item[data-type]').forEach(item => {
      item.addEventListener('dragstart', e => {
        e.dataTransfer.setData('cs/palette-type', item.dataset.type);
        e.dataTransfer.setData('text/plain', '');
        e.dataTransfer.effectAllowed = 'copy';
      });
      item.addEventListener('dblclick', () => {
        const def = this._makeDefaultCardDef(item.dataset.type);
        const { col, row } = this._viewportCenterCell();
        this.addCard(def, col, row);
      });
    });
  }

  _makeDefaultCardDef(type) {
    return {
      type,
      label:    type === 'note' ? '备注' : '模块卡片',
      col_span: 3,
      row_span: 3,
      config:   {},
    };
  }

  // ── 画布类型扩展操作 ──────────────────────────────────────────────────────
  _renderTypeActions() {
    const area = document.getElementById('csTypeActions');
    if (!area || !this._plugin?.toolbarActions) return;
    this._plugin.toolbarActions.forEach(action => {
      const btn = document.createElement('button');
      btn.className = 'cs-tb-btn';
      btn.title = action.label;
      btn.innerHTML = action.icon
        ? `<svg class="icon" width="13" height="13"><use href="${action.icon}"/></svg> ${_esc(action.label)}`
        : _esc(action.label);
      btn.addEventListener('click', () => action.handler(this));
      area.appendChild(btn);
    });
  }

  // ── 卡片管理 ──────────────────────────────────────────────────────────────
  addCard(def, col, row) {
    if (!def.id) def.id = _uuid();
    def.col_start = col || def.col_start || 1;
    def.row_start = row || def.row_start || 1;
    def.layer_id  = def.layer_id || this._layers?.getDefaultLayerId() || 'layer_default';
    this._cards.set(def.id, def);
    this._renderCard(def);
    this._connection.refresh(this._cardFrames);
    this._markDirty();
    this._checkEmpty();
    return def;
  }

  _addDefaultCard() {
    const { col, row } = this._viewportCenterCell();
    this.addCard(this._makeDefaultCardDef('note'), col, row);
  }

  removeCard(id) {
    const cf = this._cardFrames.get(id);
    if (cf) { cf.unmount(); this._cardFrames.delete(id); }
    this._cards.delete(id);
    this._layerMap.delete(id);
    this._connection.removeConnectionsFor(id);
    if (this._selectedCardId === id) this._closeBottomPanel();
    this._markDirty();
    this._checkEmpty();
  }

  _renderCard(def) {
    const gridHost = document.getElementById('csGridHost');
    const plugin   = this._plugin;

    // CardFrame（传 zoom 代理）
    const cf = new CardFrame({
      id:       def.id,
      colSpan:  def.col_span  || 3,
      rowSpan:  def.row_span  || 3,
      colStart: def.col_start || null,
      rowStart: def.row_start || null,
      grid:     this._makeGridProxy(),
      onResize: (cs, rs) => this._onCardResize(def.id, cs, rs),
      onPopOut: () => this._onCardPopOut(def.id),
      onDelete: () => this._confirmDeleteCard(def.id),
    });

    // 卡片头部
    const typeLabel = plugin?.cardTypes?.[def.type]?.label || def.type || '卡片';
    const hdr = document.createElement('div');
    hdr.className = 'cs-card-hdr';
    hdr.innerHTML = `
      <span class="cs-drag-handle" title="拖拽移位">
        <svg class="icon" width="11" height="11"><use href="#icon-apps"/></svg>
      </span>
      <span class="cs-card-title">${_esc(def.label || typeLabel)}</span>
      <span class="cs-card-type-badge">${_esc(typeLabel)}</span>
      <button class="cs-card-hdr-btn cs-card-rename-btn" title="重命名" data-cid="${def.id}">
        <svg class="icon" width="11" height="11"><use href="#icon-note"/></svg>
      </button>
      <button class="cs-card-hdr-btn cs-card-delete-btn" title="删除" data-cid="${def.id}">
        <svg class="icon" width="11" height="11"><use href="#icon-x"/></svg>
      </button>
    `;

    // 卡片正文
    const body = document.createElement('div');
    body.className = 'cs-card-body';
    if (plugin?.cardTypes?.[def.type]?.renderContent) {
      plugin.cardTypes[def.type].renderContent(body, def.config || {});
    } else {
      body.style.display = 'flex';
      body.style.alignItems = 'center';
      body.style.justifyContent = 'center';
      body.style.color = 'var(--text-faint)';
      body.style.fontSize = '11px';
      body.textContent = def.config?.text || '';
    }

    // Port 圆点（四个方向）
    ['top','bottom','left','right'].forEach(dir => {
      const port = document.createElement('div');
      port.className = `cs-port cs-port-${dir}`;
      port.dataset.port = dir;
      port.addEventListener('mousedown', e => {
        if (this._editMode) {
          e.stopPropagation();
          this._connection.startDrawing(def.id, dir, e);
        }
      });
      cf.el.appendChild(port);
    });

    cf.contentEl.appendChild(hdr);
    cf.contentEl.appendChild(body);
    cf.mount(gridHost);
    cf.setEditMode(this._editMode);

    // 事件绑定
    hdr.querySelector('.cs-drag-handle')?.addEventListener('mousedown', e => {
      if (this._editMode) this._startDrag(e, def.id, cf);
    });
    hdr.querySelector('.cs-card-rename-btn')?.addEventListener('click', async e => {
      e.stopPropagation();
      const name = await this._promptText('重命名卡片', '卡片名称', def.label || '');
      if (name !== null) {
        def.label = name;
        hdr.querySelector('.cs-card-title').textContent = name;
        this._markDirty();
        if (this._selectedCardId === def.id) this._openBottomPanel(def.id);
      }
    });
    hdr.querySelector('.cs-card-delete-btn')?.addEventListener('click', e => {
      e.stopPropagation();
      if (this._editMode) this._confirmDeleteCard(def.id);
    });

    // 点击卡片（非编辑模式）→ 底部详情
    cf.el.addEventListener('click', e => {
      if (this._editMode) return;
      if (e.target.closest('.cf-popout-btn,.cs-card-hdr-btn')) return;
      this._selectCard(def.id);
    });

    this._cardFrames.set(def.id, cf);
    this._layerMap.set(def.id, { cf, layer_id: def.layer_id });

    // 应用图层过滤
    this._layers?.applyFilter(this._layerMap);
  }

  /** GridProxy：在 snapResize 中补偿 zoom */
  _makeGridProxy() {
    const shell = this;
    const gs    = this._gridSystem;
    return {
      get _opts()     { return gs._opts; },
      get _colWidth() { return gs._colWidth; },
      snapResize(curCol, curRow, deltaX, deltaY) {
        return gs.snapResize(curCol, curRow, deltaX / shell._zoom, deltaY / shell._zoom);
      },
    };
  }

  _onCardResize(id, colSpan, rowSpan) {
    const card = this._cards.get(id);
    if (card) { card.col_span = colSpan; card.row_span = rowSpan; }
    this._connection.refresh(this._cardFrames);
    this._markDirty();
  }

  _onCardPopOut(id) {
    const card = this._cards.get(id);
    if (!card || !window.parent?.TabManager) return;
    window.parent.TabManager.open('canvas_shell', {
      canvas_gid:  this._canvasGid,
      canvas_type: this._canvasType,
      focus_card:  id,
    });
  }

  async _confirmDeleteCard(id) {
    const card = this._cards.get(id);
    const name = card?.label || '此卡片';
    const ok = await this._confirmDialog(`删除"${name}"？此操作不可撤销。`, '删除');
    if (ok) this.removeCard(id);
  }

  // ── 卡片选中 ──────────────────────────────────────────────────────────────
  _selectCard(id) {
    // 取消之前的选中状态
    if (this._selectedCardId) {
      this._cardFrames.get(this._selectedCardId)?.el.classList.remove('cs-card-selected');
    }
    this._selectedCardId = id;
    this._cardFrames.get(id)?.el.classList.add('cs-card-selected');
    this._openBottomPanel(id);
  }

  // ── 底部详情面板 ──────────────────────────────────────────────────────────
  _openBottomPanel(cardId) {
    const card = this._cards.get(cardId);
    if (!card) return;

    const panel   = document.getElementById('csBottomPanel');
    const typeTag = document.getElementById('csBottomTypeTag');
    const nameEl  = document.getElementById('csBottomCardName');
    const metaEl  = document.getElementById('csBottomMeta');
    const propsEl = document.getElementById('csBottomProps');
    const extEl   = document.getElementById('csBottomExt');

    if (!panel) return;
    panel.classList.add('cs-bottom-open');

    const cf       = this._cardFrames.get(cardId);
    const cfConfig = cf?.toConfig() || {};
    const typeLabel = this._plugin?.cardTypes?.[card.type]?.label || card.type || '卡片';
    const layer    = this._layers?.getLayerById(card.layer_id);

    if (typeTag)  typeTag.textContent = typeLabel;
    if (nameEl)   nameEl.textContent  = card.label || typeLabel;
    if (metaEl)   metaEl.innerHTML = `
      <span>列 ${cfConfig.col_start}，行 ${cfConfig.row_start}</span>
      <span>${cfConfig.col_span}×${cfConfig.row_span}</span>
      ${layer ? `<span style="color:${layer.color}">${_esc(layer.name)}</span>` : ''}
    `;

    // 基础属性
    if (propsEl) {
      const layerOpts = this._layers ? this._layers.getLayers().map(l =>
        `<option value="${l.id}" ${l.id === card.layer_id ? 'selected' : ''}>${_esc(l.name)}</option>`
      ).join('') : '';

      propsEl.innerHTML = `
        <div class="cs-prop-row">
          <span class="cs-prop-label">名称</span>
          <input class="cs-prop-value-edit" id="csBpName" value="${_esc(card.label || '')}">
        </div>
        <div class="cs-prop-row">
          <span class="cs-prop-label">类型</span>
          <span class="cs-prop-value">${_esc(typeLabel)}</span>
        </div>
        <div class="cs-prop-row">
          <span class="cs-prop-label">位置</span>
          <span class="cs-prop-value">列${cfConfig.col_start} 行${cfConfig.row_start}，跨 ${cfConfig.col_span}×${cfConfig.row_span}</span>
        </div>
        <div class="cs-prop-row">
          <span class="cs-prop-label">图层</span>
          <select id="csBpLayer" style="font-size:12px;background:var(--bg-secondary);border:1px solid var(--border-default);border-radius:3px;padding:2px 5px;color:var(--text-normal);">
            ${layerOpts}
          </select>
        </div>
      `;
      propsEl.querySelector('#csBpName')?.addEventListener('change', e => {
        card.label = e.target.value.trim();
        const hdr = this._cardFrames.get(cardId)?.el.querySelector('.cs-card-title');
        if (hdr) hdr.textContent = card.label;
        this._markDirty();
      });
      propsEl.querySelector('#csBpLayer')?.addEventListener('change', e => {
        card.layer_id = e.target.value;
        this._layerMap.set(cardId, { cf, layer_id: card.layer_id });
        this._layers?.applyFilter(this._layerMap);
        this._markDirty();
      });
    }

    // 扩展详情（由插件提供）
    if (extEl) {
      extEl.innerHTML = '';
      if (this._plugin?.cardTypes?.[card.type]?.renderDetail) {
        this._plugin.cardTypes[card.type].renderDetail(extEl, card.config || {}, (newConfig) => {
          card.config = { ...card.config, ...newConfig };
          this._markDirty();
        });
      } else {
        extEl.style.display = 'flex';
        extEl.style.alignItems = 'center';
        extEl.style.justifyContent = 'center';
        extEl.style.color = 'var(--text-faint)';
        extEl.style.fontSize = '11px';
        extEl.textContent = '此卡片类型暂无扩展详情';
      }
    }
  }

  _closeBottomPanel() {
    document.getElementById('csBottomPanel')?.classList.remove('cs-bottom-open');
    if (this._selectedCardId) {
      this._cardFrames.get(this._selectedCardId)?.el.classList.remove('cs-card-selected');
      this._selectedCardId = null;
    }
  }

  // ── 拖拽移位 ──────────────────────────────────────────────────────────────
  _startDrag(e, cardId, cf) {
    e.preventDefault();
    e.stopPropagation();

    const gridHost = document.getElementById('csGridHost');
    const card     = this._cards.get(cardId);
    if (!card || !gridHost) return;

    const colSpan  = cf._currentColSpan();
    const rowSpan  = cf._currentRowSpan();

    // 占位符
    const ph = document.createElement('div');
    ph.className = 'cs-drop-placeholder';
    ph.style.gridColumn = `${card.col_start} / span ${colSpan}`;
    ph.style.gridRow    = `${card.row_start} / span ${rowSpan}`;
    gridHost.appendChild(ph);

    cf.el.classList.add('cs-card-moving');

    const onMove = me => {
      const world = this._screenToWorld(me.clientX, me.clientY);
      const { col, row } = this._worldToGridCell(world.x, world.y);
      ph.style.gridColumn = `${col} / span ${colSpan}`;
      ph.style.gridRow    = `${row} / span ${rowSpan}`;
      this._updateGuides(col, row, colSpan, rowSpan, cardId);
    };

    const onUp = me => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);

      const world = this._screenToWorld(me.clientX, me.clientY);
      const { col, row } = this._worldToGridCell(world.x, world.y);

      cf.setPosition(col, row);
      cf.el.classList.remove('cs-card-moving');
      ph.remove();
      this._clearGuides();

      card.col_start = col;
      card.row_start = row;
      this._connection.refresh(this._cardFrames);
      this._markDirty();
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  // ── 对齐参考线 ────────────────────────────────────────────────────────────
  _clearGuides() {
    if (this._guideOverlay) this._guideOverlay.innerHTML = '';
  }

  _updateGuides(col, row, colSpan, rowSpan, excludeId) {
    const gs = this._gridSystem;
    if (!gs || !this._guideOverlay) return;
    this._clearGuides();

    const t   = gs.cellPixelRect(col, row, colSpan, rowSpan);
    const tL  = t.x,            tR  = t.x + t.w;
    const tT  = t.y,            tB  = t.y + t.h;
    const tCX = t.x + t.w / 2,  tCY = t.y + t.h / 2;

    const vGuides = new Set();
    const hGuides = new Set();
    const TOL     = 3;

    const gridHost = document.getElementById('csGridHost');
    const ghRect   = gridHost?.getBoundingClientRect();

    document.querySelectorAll('.cf-card').forEach(el => {
      if (el.dataset.cfId === excludeId) return;
      if (el.classList.contains('cs-card-moving')) return;

      const r  = el.getBoundingClientRect();
      const zoom = this._zoom;
      const oL = (r.left - ghRect.left) / zoom;
      const oT = (r.top  - ghRect.top)  / zoom;
      const oR = oL + r.width  / zoom;
      const oB = oT + r.height / zoom;
      const oCX = (oL + oR) / 2;
      const oCY = (oT + oB) / 2;

      [[tL,oL],[tL,oR],[tR,oL],[tR,oR],[tCX,oCX]].forEach(([a,b]) => {
        if (Math.abs(a - b) <= TOL) vGuides.add(Math.round(b));
      });
      [[tT,oT],[tT,oB],[tB,oT],[tB,oB],[tCY,oCY]].forEach(([a,b]) => {
        if (Math.abs(a - b) <= TOL) hGuides.add(Math.round(b));
      });
    });

    const NS = 'http://www.w3.org/2000/svg';
    const col_  = 'var(--cs-guide-color, #7b61ff)';
    const svgW  = gridHost?.offsetWidth  || 4000;
    const svgH  = gridHost?.offsetHeight || 3000;

    vGuides.forEach(x => {
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', x); line.setAttribute('y1', 0);
      line.setAttribute('x2', x); line.setAttribute('y2', svgH);
      line.setAttribute('stroke', col_);
      line.setAttribute('stroke-width', '1');
      line.setAttribute('stroke-dasharray', '5 3');
      line.setAttribute('opacity', '0.7');
      this._guideOverlay.appendChild(line);
    });
    hGuides.forEach(y => {
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', 0);    line.setAttribute('y1', y);
      line.setAttribute('x2', svgW); line.setAttribute('y2', y);
      line.setAttribute('stroke', col_);
      line.setAttribute('stroke-width', '1');
      line.setAttribute('stroke-dasharray', '5 3');
      line.setAttribute('opacity', '0.7');
      this._guideOverlay.appendChild(line);
    });
  }

  // ── 图层变化回调 ──────────────────────────────────────────────────────────
  _onLayerChange() {
    this._layers.applyFilter(this._layerMap);
    // 更新连线透明度
    const visibleSet = new Set(this._layers.getVisibleLayerIds());
    document.querySelectorAll('[data-conn-id]').forEach(el => {
      const connId = el.dataset.connId;
      const conn   = this._connection._connections.get(connId);
      if (!conn) return;
      const fromCard = this._cards.get(conn.from);
      const toCard   = this._cards.get(conn.to);
      const hidden   = fromCard && !visibleSet.has(fromCard.layer_id)
                    || toCard   && !visibleSet.has(toCard.layer_id);
      el.setAttribute('stroke-opacity', hidden ? '0.08' : '0.85');
    });
    this._markDirty();
  }

  // ── 空状态 ────────────────────────────────────────────────────────────────
  _checkEmpty() {
    document.getElementById('csViewportEmpty')?.classList.toggle('hidden', this._cards.size > 0);
  }

  // ── 公开 API（供类型插件调用）────────────────────────────────────────────

  /**
   * 批量重置卡片和连线（由类型插件 onInit 调用）
   */
  reloadCards(cards, connections) {
    this._cardFrames.forEach(cf => cf.unmount());
    this._cardFrames.clear();
    this._cards.clear();
    this._layerMap.clear();
    this._connection.deserialize(connections || []);
    (cards || []).forEach(card => {
      this._cards.set(card.id, card);
      this._renderCard(card);
    });
    this._connection.refresh(this._cardFrames);
    this._checkEmpty();
  }

  /**
   * 高亮节点运行状态（供流程引擎轮询时调用）
   * @param {string} cardId
   * @param {'running'|'done'|'fail'|''} status  空字符串 → 清除
   */
  highlightNode(cardId, status) {
    const cf = this._cardFrames.get(cardId);
    if (!cf) return;
    cf.el.classList.remove('cs-node-running', 'cs-node-done', 'cs-node-fail');
    if (status) cf.el.classList.add(`cs-node-${status}`);
  }

  clearNodeHighlights() {
    this._cardFrames.forEach(cf => {
      cf.el.classList.remove('cs-node-running', 'cs-node-done', 'cs-node-fail');
    });
  }

  // ── 面板切换 ──────────────────────────────────────────────────────────────
  _togglePanel(side) {
    const el = document.getElementById(side === 'left' ? 'csLeftPanel' : 'csRightPanel');
    el?.classList.toggle('cs-panel-collapsed');
  }

  _toggleLayerPanel(btnEl) {
    const panel = document.getElementById('csLayerPanel');
    if (!panel) return;
    if (!panel.classList.contains('hidden')) { panel.classList.add('hidden'); return; }
    const rect = btnEl.getBoundingClientRect();
    panel.style.top   = `${rect.bottom + 4}px`;
    panel.style.right = `${window.innerWidth - rect.right}px`;
    panel.classList.remove('hidden');
    this._layers?.renderPanel(document.getElementById('csLayerList'));
    // 点击外部关闭
    setTimeout(() => {
      const close = e => { if (!panel.contains(e.target)) { panel.classList.add('hidden'); document.removeEventListener('click', close); } };
      document.addEventListener('click', close);
    }, 0);
  }

  // ── 网格设置面板 ──────────────────────────────────────────────────────────
  _toggleGsPanel(btnEl) {
    const panel = document.getElementById('csGsPanel');
    if (!panel) return;
    if (!panel.classList.contains('hidden')) { panel.classList.add('hidden'); return; }
    const cfg = this._loadGridConfig();
    document.getElementById('csGsCols').value    = cfg.cols;
    document.getElementById('csGsRowH').value    = cfg.rowHeight;
    document.getElementById('csGsGap').value     = cfg.gap;
    document.getElementById('csGsOpacity').value = cfg.overlayOpacity;
    document.getElementById('csGsOpacityVal').textContent = Math.round(cfg.overlayOpacity * 100) + '%';
    document.getElementById('csGsColor').value   = cfg.overlayColor;
    const rect = btnEl.getBoundingClientRect();
    panel.style.top   = `${rect.bottom + 4}px`;
    panel.style.right = `${window.innerWidth - rect.right}px`;
    panel.classList.remove('hidden');
  }

  _applyGridSettings() {
    const cfg = {
      cols:           Math.max(4,   Math.min(48,  parseInt(document.getElementById('csGsCols').value)    || 24)),
      rowHeight:      Math.max(60,  Math.min(200, parseInt(document.getElementById('csGsRowH').value)    || 80)),
      gap:            Math.max(4,   Math.min(32,  parseInt(document.getElementById('csGsGap').value)     || 12)),
      overlayOpacity: Math.max(0.1, Math.min(1,   parseFloat(document.getElementById('csGsOpacity').value) || 0.35)),
      overlayColor:   document.getElementById('csGsColor').value || '#888888',
    };
    this._saveGridConfig(cfg);
    this._gridSystem?.setOptions({ ...cfg, overlayVisible: this._editMode });
    this._connection?.refresh(this._cardFrames);
    document.getElementById('csGsPanel')?.classList.add('hidden');
    this._markDirty();
  }

  // ── 自定义对话框（Electron renderer 不支持 prompt/confirm）───────────────
  _inputModalResolve  = null;
  _confirmModalResolve = null;

  _promptText(title, placeholder, defaultValue = '') {
    return new Promise(resolve => {
      this._inputModalResolve = resolve;
      const modal = document.getElementById('csInputModal');
      document.getElementById('csInputModalTitle').textContent = title;
      const field = document.getElementById('csInputModalField');
      field.placeholder = placeholder || '';
      field.value = defaultValue;
      modal.classList.remove('hidden');
      setTimeout(() => field.focus(), 50);
    });
  }
  _resolveInputModal(val) {
    document.getElementById('csInputModal')?.classList.add('hidden');
    this._inputModalResolve?.(val);
    this._inputModalResolve = null;
  }

  _confirmDialog(message, confirmLabel = '确认') {
    return new Promise(resolve => {
      this._confirmModalResolve = resolve;
      const modal = document.getElementById('csConfirmModal');
      document.getElementById('csConfirmModalMsg').textContent = message;
      document.getElementById('csConfirmModalOk').textContent  = confirmLabel;
      modal.classList.remove('hidden');
    });
  }
  _resolveConfirmModal(bool) {
    document.getElementById('csConfirmModal')?.classList.add('hidden');
    this._confirmModalResolve?.(bool);
    this._confirmModalResolve = null;
  }
}

// ── 启动 ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  window._canvasShell = new CanvasShell();
  window._canvasShell.init().catch(err => console.error('[CanvasShell] init error:', err));
});
