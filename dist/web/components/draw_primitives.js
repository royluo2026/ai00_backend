'use strict';
/**
 * DrawPrimitives — SVG 绘制原语组件
 *
 * 供图片标注（容器卡片 4.7）和画布类型共用。
 * 基于内联 SVG，标注数据可序列化为 JSON。
 *
 * 支持形状：
 *   rect       矩形
 *   circle     圆形
 *   line       直线
 *   arrow      带箭头的线
 *   text       文字标注
 *   flow_node  流程节点（圆角矩形 + 内文字）
 *
 * 用法：
 *   const dp = new DrawPrimitives(svgElement, { editable: true });
 *   dp.setTool('rect');
 *   dp.setColor('#e74c3c');
 *   dp.onChange(shapes => console.log(shapes));
 *   // 序列化
 *   const json = dp.toJSON();
 *   dp.fromJSON(json);
 */
class DrawPrimitives {
  constructor(svgEl, options = {}) {
    this._svg  = svgEl;
    this._opts = {
      editable: true,
      ...options,
    };

    this._shapes       = [];
    this._tool         = 'select';
    this._color        = '#e74c3c';
    this._strokeWidth  = 2;
    this._onChangeCb   = null;

    // 拖拽绘制状态
    this._drawing      = false;
    this._drawStart    = null;
    this._tempEl       = null;

    this._shapesLayer  = null;
    this._defsEl       = null;

    this._setupSVG();
    if (this._opts.editable) this._bindEvents();
  }

  // ── SVG 初始化 ─────────────────────────────────────────────────────────────
  _setupSVG() {
    const NS = 'http://www.w3.org/2000/svg';

    // defs：箭头 marker（颜色随绘制颜色动态更新）
    this._defsEl = document.createElementNS(NS, 'defs');
    this._defsEl.innerHTML = `
      <marker id="dp-arrow-${this._uid()}" markerWidth="10" markerHeight="7"
              refX="8" refY="3.5" orient="auto">
        <polygon id="dp-arrow-polygon" points="0 0,10 3.5,0 7"
                 fill="${this._color}"/>
      </marker>`;
    this._arrowMarkerId = this._defsEl.querySelector('marker').id;
    this._svg.prepend(this._defsEl);

    // 形状层
    this._shapesLayer = document.createElementNS(NS, 'g');
    this._shapesLayer.setAttribute('class', 'dp-shapes');
    this._svg.appendChild(this._shapesLayer);

    // 光标
    this._svg.style.cursor = 'default';
  }

  _uid() {
    return Math.random().toString(36).slice(2, 8);
  }

  // ── 事件绑定 ──────────────────────────────────────────────────────────────
  _bindEvents() {
    this._svg.addEventListener('mousedown', this._onMouseDown.bind(this));
    this._svg.addEventListener('mousemove', this._onMouseMove.bind(this));
    this._svg.addEventListener('mouseup',   this._onMouseUp.bind(this));
  }

  _svgPoint(e) {
    const rect = this._svg.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  _onMouseDown(e) {
    if (!this._opts.editable || this._tool === 'select') return;
    e.preventDefault();
    this._drawing   = true;
    this._drawStart = this._svgPoint(e);
  }

  _onMouseMove(e) {
    if (!this._drawing || !this._drawStart) return;
    const p = this._svgPoint(e);
    this._renderTemp(this._drawStart, p);
  }

  _onMouseUp(e) {
    if (!this._drawing) return;
    this._drawing = false;
    const p = this._svgPoint(e);
    const s = this._drawStart;
    this._drawStart = null;
    this._removeTemp();

    // 太小的拖拽忽略（防误触）
    if (Math.abs(p.x - s.x) < 4 && Math.abs(p.y - s.y) < 4 && this._tool !== 'text') return;

    const shape = this._makeShape(s, p);
    if (shape) {
      this._shapes.push(shape);
      this._renderShape(shape, this._shapesLayer);
      this._onChangeCb?.(this._shapes);
    }
  }

  // ── 形状数据构造 ───────────────────────────────────────────────────────────
  _makeShape(s, p) {
    const id   = `dp-${Date.now()}-${this._uid()}`;
    const base = {
      id,
      type:        this._tool,
      color:       this._color,
      strokeWidth: this._strokeWidth,
    };

    switch (this._tool) {
      case 'rect':
        return {
          ...base,
          x: Math.min(s.x, p.x), y: Math.min(s.y, p.y),
          w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y),
          fill: 'none',
        };

      case 'circle': {
        const r = Math.sqrt((p.x - s.x) ** 2 + (p.y - s.y) ** 2) / 2;
        return {
          ...base,
          cx: (s.x + p.x) / 2, cy: (s.y + p.y) / 2,
          r:  Math.max(r, 4),
          fill: 'none',
        };
      }

      case 'line':
        return { ...base, x1: s.x, y1: s.y, x2: p.x, y2: p.y };

      case 'arrow':
        return { ...base, x1: s.x, y1: s.y, x2: p.x, y2: p.y };

      case 'flow_node':
        return {
          ...base,
          x: Math.min(s.x, p.x), y: Math.min(s.y, p.y),
          w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y),
          text: '', fill: 'none', rx: 8,
        };

      case 'text':
        return { ...base, x: s.x, y: s.y, text: '文字', fontSize: 14 };

      default:
        return null;
    }
  }

  // ── 临时预览 ──────────────────────────────────────────────────────────────
  _renderTemp(s, p) {
    this._removeTemp();
    const shape = this._makeShape(s, p);
    if (!shape) return;
    const el = this._buildSVGElement(shape);
    if (el) {
      el.style.opacity = '0.5';
      el.classList.add('dp-temp');
      this._shapesLayer.appendChild(el);
      this._tempEl = el;
    }
  }

  _removeTemp() {
    this._tempEl?.remove();
    this._tempEl = null;
  }

  // ── SVG 元素构建 ──────────────────────────────────────────────────────────
  _buildSVGElement(shape) {
    const NS = 'http://www.w3.org/2000/svg';
    let el;

    switch (shape.type) {
      case 'rect': {
        el = document.createElementNS(NS, 'rect');
        el.setAttribute('x',      shape.x);
        el.setAttribute('y',      shape.y);
        el.setAttribute('width',  shape.w);
        el.setAttribute('height', shape.h);
        el.setAttribute('rx',     shape.rx || 0);
        el.setAttribute('fill',   shape.fill || 'none');
        el.setAttribute('stroke', shape.color);
        el.setAttribute('stroke-width', shape.strokeWidth);
        break;
      }

      case 'circle': {
        el = document.createElementNS(NS, 'circle');
        el.setAttribute('cx',     shape.cx);
        el.setAttribute('cy',     shape.cy);
        el.setAttribute('r',      shape.r);
        el.setAttribute('fill',   shape.fill || 'none');
        el.setAttribute('stroke', shape.color);
        el.setAttribute('stroke-width', shape.strokeWidth);
        break;
      }

      case 'line': {
        el = document.createElementNS(NS, 'line');
        el.setAttribute('x1', shape.x1); el.setAttribute('y1', shape.y1);
        el.setAttribute('x2', shape.x2); el.setAttribute('y2', shape.y2);
        el.setAttribute('stroke', shape.color);
        el.setAttribute('stroke-width', shape.strokeWidth);
        el.setAttribute('stroke-linecap', 'round');
        break;
      }

      case 'arrow': {
        // 更新 marker 颜色
        const polygon = this._defsEl?.querySelector('polygon');
        if (polygon) polygon.setAttribute('fill', shape.color);

        el = document.createElementNS(NS, 'line');
        el.setAttribute('x1', shape.x1); el.setAttribute('y1', shape.y1);
        el.setAttribute('x2', shape.x2); el.setAttribute('y2', shape.y2);
        el.setAttribute('stroke', shape.color);
        el.setAttribute('stroke-width', shape.strokeWidth);
        el.setAttribute('stroke-linecap', 'round');
        el.setAttribute('marker-end', `url(#${this._arrowMarkerId})`);
        break;
      }

      case 'flow_node': {
        // g 包裹 rect + text
        const g    = document.createElementNS(NS, 'g');
        const rect = document.createElementNS(NS, 'rect');
        rect.setAttribute('x',      shape.x);
        rect.setAttribute('y',      shape.y);
        rect.setAttribute('width',  shape.w);
        rect.setAttribute('height', shape.h);
        rect.setAttribute('rx',     shape.rx || 8);
        rect.setAttribute('fill',   shape.fill || 'none');
        rect.setAttribute('stroke', shape.color);
        rect.setAttribute('stroke-width', shape.strokeWidth);
        g.appendChild(rect);
        if (shape.text) {
          const text = document.createElementNS(NS, 'text');
          text.setAttribute('x',                 shape.x + shape.w / 2);
          text.setAttribute('y',                 shape.y + shape.h / 2);
          text.setAttribute('text-anchor',        'middle');
          text.setAttribute('dominant-baseline',  'middle');
          text.setAttribute('fill',               shape.color);
          text.setAttribute('font-size',          shape.fontSize || 13);
          text.textContent = shape.text;
          g.appendChild(text);
        }
        g.dataset.shapeId = shape.id;
        return g;
      }

      case 'text': {
        el = document.createElementNS(NS, 'text');
        el.setAttribute('x',         shape.x);
        el.setAttribute('y',         shape.y);
        el.setAttribute('fill',      shape.color);
        el.setAttribute('font-size', shape.fontSize || 14);
        el.setAttribute('font-family', 'system-ui, sans-serif');
        el.textContent = shape.text;
        break;
      }

      default:
        return null;
    }

    if (el) el.dataset.shapeId = shape.id;
    return el;
  }

  // ── 渲染（单个）──────────────────────────────────────────────────────────
  _renderShape(shape, layer) {
    const el = this._buildSVGElement(shape);
    if (el) layer.appendChild(el);
    return el;
  }

  // ── 公开 API ──────────────────────────────────────────────────────────────

  /** 全量重绘 */
  render(shapes) {
    this._shapes = shapes || [];
    this._shapesLayer.innerHTML = '';
    this._shapes.forEach(s => this._renderShape(s, this._shapesLayer));
  }

  /** 清空所有形状 */
  clear() {
    this._shapes = [];
    this._shapesLayer.innerHTML = '';
    this._onChangeCb?.(this._shapes);
  }

  /** 设置当前工具 */
  setTool(tool) {
    this._tool = tool;
    this._svg.style.cursor = tool === 'select' ? 'default' : 'crosshair';
  }

  /** 设置绘制颜色（hex）*/
  setColor(hex) {
    this._color = hex;
  }

  /** 设置线宽 */
  setStrokeWidth(n) {
    this._strokeWidth = n;
  }

  /** 切换可编辑状态 */
  setEditable(bool) {
    this._opts.editable = bool;
    this._svg.style.cursor = bool && this._tool !== 'select' ? 'crosshair' : 'default';
  }

  /** 注册变更回调 */
  onChange(cb) {
    this._onChangeCb = cb;
  }

  /** 序列化为 JSON */
  toJSON() {
    return JSON.parse(JSON.stringify(this._shapes));
  }

  /** 从 JSON 加载并渲染 */
  fromJSON(arr) {
    this.render(arr || []);
  }

  /** 删除指定 id 的形状 */
  removeShape(id) {
    this._shapes = this._shapes.filter(s => s.id !== id);
    this._shapesLayer.querySelector(`[data-shape-id="${id}"]`)?.remove();
    this._onChangeCb?.(this._shapes);
  }
}

window.DrawPrimitives = DrawPrimitives;

