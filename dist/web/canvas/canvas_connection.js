'use strict';
/**
 * ConnectionLayer — SVG 连线管理
 *
 * 管理画布卡片间的有向连线：
 *   - add/remove/serialize/deserialize
 *   - refresh：根据卡片当前 DOM 位置重算路径
 *   - 交互：点击 port 圆点开始拉线，松手连接目标 port
 *   - 路径类型：bezier 曲线（简洁、适合 flow 图）
 *
 * 坐标系：gs-container（csGridHost）的 local 坐标（世界坐标系内）。
 * getBoundingClientRect 返回屏幕像素，需除以 zoom 转换到世界坐标。
 */
class ConnectionLayer {
  constructor(svgEl, containerEl, getZoom) {
    this._svg       = svgEl;         // <svg> 叠层元素
    this._container = containerEl;   // gs-container（坐标原点）
    this._getZoom   = getZoom;       // () => currentZoom

    this._connections = new Map();   // id → {id, from, fromPort, to, toPort, label}
    this._cardFrames  = null;        // Map<id, CardFrame>（由 CanvasShell 注入）

    // 拉线交互状态
    this._drawing     = false;
    this._drawFrom    = null;  // {cardId, port}
    this._tempLine    = null;  // 临时 SVG path

    // SVG defs（箭头 marker）
    this._initDefs();
  }

  // ── 初始化 SVG defs（箭头）────────────────────────────────────────────────
  _initDefs() {
    const NS = 'http://www.w3.org/2000/svg';
    const defs = document.createElementNS(NS, 'defs');

    const marker = document.createElementNS(NS, 'marker');
    marker.setAttribute('id', 'cs-arrow');
    marker.setAttribute('viewBox', '0 0 10 10');
    marker.setAttribute('refX', '9');
    marker.setAttribute('refY', '5');
    marker.setAttribute('markerWidth', '6');
    marker.setAttribute('markerHeight', '6');
    marker.setAttribute('orient', 'auto-start-reverse');

    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
    path.setAttribute('fill', 'var(--cs-connection-color, #7b61ff)');

    marker.appendChild(path);
    defs.appendChild(marker);
    this._svg.appendChild(defs);
  }

  // ── 连线 CRUD ──────────────────────────────────────────────────────────────

  addConnection(conn) {
    // conn: {id, from, fromPort, to, toPort, label?}
    this._connections.set(conn.id, { ...conn });
    if (this._cardFrames) this.refresh(this._cardFrames);
  }

  removeConnection(id) {
    this._connections.delete(id);
    const el = this._svg.querySelector(`[data-conn-id="${id}"]`);
    el?.remove();
    const lbl = this._svg.querySelector(`[data-conn-label="${id}"]`);
    lbl?.remove();
  }

  removeConnectionsFor(cardId) {
    const toRemove = [];
    this._connections.forEach((conn, id) => {
      if (conn.from === cardId || conn.to === cardId) toRemove.push(id);
    });
    toRemove.forEach(id => this.removeConnection(id));
  }

  getConnections() {
    return Array.from(this._connections.values());
  }

  // ── 刷新所有连线路径 ──────────────────────────────────────────────────────
  refresh(cardFrames) {
    this._cardFrames = cardFrames;

    this._connections.forEach(conn => {
      this._renderConnection(conn);
    });
  }

  _renderConnection(conn) {
    const NS    = 'http://www.w3.org/2000/svg';
    const from  = this._getPortWorldPos(conn.from,  conn.fromPort  || 'right');
    const to    = this._getPortWorldPos(conn.to,    conn.toPort    || 'left');
    if (!from || !to) return;

    const d = this._bezierPath(from, to);

    // 找或创建 path 元素
    let pathEl = this._svg.querySelector(`[data-conn-id="${conn.id}"]`);
    if (!pathEl) {
      pathEl = document.createElementNS(NS, 'path');
      pathEl.setAttribute('data-conn-id', conn.id);
      pathEl.setAttribute('fill', 'none');
      pathEl.setAttribute('stroke', 'var(--cs-connection-color, #7b61ff)');
      pathEl.setAttribute('stroke-width', '2');
      pathEl.setAttribute('stroke-opacity', '0.85');
      pathEl.setAttribute('marker-end', 'url(#cs-arrow)');
      pathEl.style.cursor = 'pointer';
      pathEl.addEventListener('click', e => {
        e.stopPropagation();
        this._selectConnection(conn.id);
      });
      this._svg.appendChild(pathEl);
    }
    pathEl.setAttribute('d', d);

    // 标签
    if (conn.label) {
      const midX = (from.x + to.x) / 2;
      const midY = (from.y + to.y) / 2;
      let lblEl = this._svg.querySelector(`[data-conn-label="${conn.id}"]`);
      if (!lblEl) {
        lblEl = document.createElementNS(NS, 'text');
        lblEl.setAttribute('data-conn-label', conn.id);
        lblEl.setAttribute('text-anchor', 'middle');
        lblEl.setAttribute('font-size', '10');
        lblEl.setAttribute('fill', 'var(--text-muted, #6e6e6e)');
        this._svg.appendChild(lblEl);
      }
      lblEl.setAttribute('x', midX);
      lblEl.setAttribute('y', midY - 6);
      lblEl.textContent = conn.label;
    }
  }

  // bezier 曲线路径（从 from port 流向 to port）
  _bezierPath(from, to) {
    const dx = Math.max(60, Math.abs(to.x - from.x) * 0.5);
    const dy = Math.max(60, Math.abs(to.y - from.y) * 0.5);

    // 根据端口方向决定控制点
    const c1 = this._portOffset(from, dx, dy);
    const c2 = this._portOffset(to, dx, dy, true);

    return `M ${from.x},${from.y} C ${c1.x},${c1.y} ${c2.x},${c2.y} ${to.x},${to.y}`;
  }

  _portOffset({ x, y, port }, dx, dy, inward = false) {
    const sign = inward ? -1 : 1;
    switch (port) {
      case 'right':  return { x: x + sign * dx, y };
      case 'left':   return { x: x - sign * dx, y };
      case 'bottom': return { x, y: y + sign * dy };
      case 'top':    return { x, y: y - sign * dy };
      default:       return { x: x + sign * dx, y };
    }
  }

  // ── Port 世界坐标 ──────────────────────────────────────────────────────────
  _getPortWorldPos(cardId, portName) {
    if (!this._cardFrames) return null;
    const cf = this._cardFrames.get(cardId);
    if (!cf) return null;

    const cardRect = cf.el.getBoundingClientRect();
    const contRect = this._container.getBoundingClientRect();
    const zoom     = this._getZoom();

    const relX = (cardRect.left - contRect.left) / zoom;
    const relY = (cardRect.top  - contRect.top)  / zoom;
    const w    = cardRect.width  / zoom;
    const h    = cardRect.height / zoom;

    let x, y;
    switch (portName) {
      case 'top':    x = relX + w / 2; y = relY;         break;
      case 'bottom': x = relX + w / 2; y = relY + h;     break;
      case 'left':   x = relX;         y = relY + h / 2; break;
      case 'right':  x = relX + w;     y = relY + h / 2; break;
      default:       x = relX + w / 2; y = relY + h / 2;
    }
    return { x, y, port: portName };
  }

  // ── 选中连线 ──────────────────────────────────────────────────────────────
  _selectConnection(id) {
    // 简单：高亮选中，支持 Delete 键删除
    this._svg.querySelectorAll('[data-conn-id]').forEach(el => {
      el.setAttribute('stroke-width', el.dataset.connId === id ? '3' : '2');
      el.setAttribute('stroke-opacity', el.dataset.connId === id ? '1' : '0.85');
    });
    this._selectedConnId = id;
  }

  deselectAll() {
    this._svg.querySelectorAll('[data-conn-id]').forEach(el => {
      el.setAttribute('stroke-width', '2');
      el.setAttribute('stroke-opacity', '0.85');
    });
    this._selectedConnId = null;
  }

  deleteSelected() {
    if (this._selectedConnId) this.removeConnection(this._selectedConnId);
  }

  // ── 拉线交互（port → port）────────────────────────────────────────────────
  startDrawing(fromCardId, fromPort, e) {
    this._drawing  = true;
    this._drawFrom = { cardId: fromCardId, port: fromPort };

    const NS = 'http://www.w3.org/2000/svg';
    this._tempLine = document.createElementNS(NS, 'path');
    this._tempLine.setAttribute('fill', 'none');
    this._tempLine.setAttribute('stroke', 'var(--cs-connection-color, #7b61ff)');
    this._tempLine.setAttribute('stroke-width', '2');
    this._tempLine.setAttribute('stroke-dasharray', '6 3');
    this._tempLine.setAttribute('stroke-opacity', '0.6');
    this._svg.appendChild(this._tempLine);

    const onMove = me => this._onDrawMove(me);
    const onUp   = me => this._onDrawUp(me, onMove, onUp);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  _onDrawMove(e) {
    if (!this._drawing || !this._tempLine) return;
    const from = this._getPortWorldPos(this._drawFrom.cardId, this._drawFrom.port);
    if (!from) return;

    const contRect = this._container.getBoundingClientRect();
    const zoom     = this._getZoom();
    const to = {
      x: (e.clientX - contRect.left) / zoom,
      y: (e.clientY - contRect.top)  / zoom,
      port: 'left',
    };
    this._tempLine.setAttribute('d', this._bezierPath(from, to));
  }

  _onDrawUp(e, onMove, onUp) {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    this._tempLine?.remove();
    this._tempLine = null;
    this._drawing  = false;

    // 检查鼠标是否在某个 port 上
    const target = document.elementFromPoint(e.clientX, e.clientY);
    if (!target?.classList.contains('cs-port')) { this._drawFrom = null; return; }

    const toCardId = target.closest('.cf-card')?.dataset.cfId;
    const toPort   = target.dataset.port;
    if (!toCardId || toCardId === this._drawFrom.cardId) { this._drawFrom = null; return; }

    const id = `conn_${Date.now()}`;
    this.addConnection({
      id,
      from:     this._drawFrom.cardId,
      fromPort: this._drawFrom.port,
      to:       toCardId,
      toPort:   toPort || 'left',
    });
    this._drawFrom = null;
  }

  cancelDrawing() {
    this._drawing = false;
    this._tempLine?.remove();
    this._tempLine = null;
    this._drawFrom = null;
  }

  // ── 序列化 ────────────────────────────────────────────────────────────────
  serialize() {
    return Array.from(this._connections.values());
  }

  deserialize(connections = []) {
    this._connections.clear();
    // 清除旧路径（保留 defs）
    this._svg.querySelectorAll('[data-conn-id],[data-conn-label]').forEach(el => el.remove());
    connections.forEach(c => this._connections.set(c.id, { ...c }));
  }
}

window.ConnectionLayer = ConnectionLayer;
