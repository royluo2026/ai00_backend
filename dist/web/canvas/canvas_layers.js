'use strict';
/**
 * LayerManager — 图层管理
 *
 * 管理画布图层（layer）：
 *   - 图层 CRUD（add/remove/rename）
 *   - 可见性控制（setLayerVisible → 应用到 DOM）
 *   - 渲染图层面板列表
 */
class LayerManager {
  constructor(layers = [], onLayerChange = null) {
    this._layers = layers.length
      ? layers.map(l => ({ ...l }))
      : [{ id: 'layer_default', name: '默认层', visible: true, color: '#888888' }];
    this._onChange = onLayerChange;  // () => void — 通知 Shell 刷新连线透明度等
    this._cardFrames = null;         // 注入：Map<cardId, {cf, layer_id}>
  }

  // ── 图层 CRUD ──────────────────────────────────────────────────────────────

  addLayer(name, color = '#888888') {
    const id = `layer_${Date.now()}`;
    this._layers.push({ id, name: name || '新图层', visible: true, color });
    this._onChange?.();
    return id;
  }

  removeLayer(layerId) {
    if (this._layers.length <= 1) return false;
    const idx = this._layers.findIndex(l => l.id === layerId);
    if (idx === -1) return false;
    this._layers.splice(idx, 1);
    this._onChange?.();
    return true;
  }

  renameLayer(layerId, name) {
    const layer = this._layers.find(l => l.id === layerId);
    if (layer) { layer.name = name; this._onChange?.(); }
  }

  getLayers()    { return this._layers; }
  getLayerById(id) { return this._layers.find(l => l.id === id) || null; }
  getDefaultLayerId() { return this._layers[0]?.id || 'layer_default'; }

  // ── 可见性 ────────────────────────────────────────────────────────────────

  setLayerVisible(layerId, bool) {
    const layer = this._layers.find(l => l.id === layerId);
    if (!layer) return;
    layer.visible = bool;
    if (this._cardFrames) this.applyFilter(this._cardFrames);
    this._onChange?.();
  }

  getVisibleLayerIds() {
    return this._layers.filter(l => l.visible).map(l => l.id);
  }

  isLayerVisible(layerId) {
    const layer = this._layers.find(l => l.id === layerId);
    return layer ? layer.visible : true;
  }

  // ── 应用过滤到 DOM ────────────────────────────────────────────────────────
  /**
   * @param {Map<cardId, {cf: CardFrame, layer_id: string}>} cardMap
   */
  applyFilter(cardMap) {
    this._cardFrames = cardMap;
    const visibleSet = new Set(this.getVisibleLayerIds());
    cardMap.forEach(({ cf, layer_id }) => {
      const hidden = !visibleSet.has(layer_id);
      cf.el.style.opacity        = hidden ? '0.08' : '';
      cf.el.style.pointerEvents  = hidden ? 'none' : '';
    });
  }

  // ── 渲染图层面板 ──────────────────────────────────────────────────────────
  renderPanel(listEl) {
    listEl.innerHTML = '';
    this._layers.forEach(layer => {
      const item = document.createElement('div');
      item.className = `cs-layer-item${layer.visible ? '' : ' cs-layer-hidden'}`;
      item.dataset.layerId = layer.id;
      item.innerHTML = `
        <span class="cs-layer-swatch" style="background:${layer.color}"></span>
        <span class="cs-layer-name">${_escHtml(layer.name)}</span>
        <button class="cs-layer-vis-btn" title="${layer.visible ? '隐藏图层' : '显示图层'}">
          <svg class="icon" width="12" height="12">
            <use href="${layer.visible ? '#icon-check' : '#icon-x'}"/>
          </svg>
        </button>
      `;
      item.querySelector('.cs-layer-vis-btn').addEventListener('click', e => {
        e.stopPropagation();
        this.setLayerVisible(layer.id, !layer.visible);
        this.renderPanel(listEl);
      });
      listEl.appendChild(item);
    });
  }

  // ── 序列化 ────────────────────────────────────────────────────────────────
  serialize() {
    return this._layers.map(l => ({ ...l }));
  }
}

function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

window.LayerManager = LayerManager;
