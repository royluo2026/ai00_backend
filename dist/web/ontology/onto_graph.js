/**
 * web/ontology/onto_graph.js
 * Canvas 力导向关系图谱：展示本体类层级 + 对象属性关系
 */
'use strict';

class OntoGraph {
  constructor(canvas, onClick) {
    this._canvas  = canvas;
    this._ctx     = canvas.getContext('2d');
    this._onClick = onClick;   // (gid) => void

    this._nodes = [];   // { id, label, color, x, y, vx, vy, r, abstract }
    this._edges = [];   // { s, t, label, type: 'inherit'|'relation' }
    this._sel   = null; // selected gid

    this._tx = 0; this._ty = 0; this._scale = 1;
    this._alpha = 1;
    this._raf   = null;

    this._drag = null;   // { nodeIdx, ox, oy }
    this._pan  = null;   // { sx, sy, tx0, ty0 }

    this._bindEvents();
    this._watchResize();
  }

  // ── 公开 API ──────────────────────────────────────────────────────────────

  setData(classes, relations) {
    const W = this._canvas.width, H = this._canvas.height;
    const cx = W / 2, cy = H / 2;
    const n  = classes.length || 1;

    this._nodes = classes.map((c, i) => {
      const angle = (2 * Math.PI * i) / n;
      const rad   = Math.min(W, H) * 0.22;   // 更紧凑的初始圆
      return {
        id:       c.gid,
        label:    c.label_zh || c.name,
        color:    c.color || '#6b7280',
        abstract: c.is_abstract || false,
        x: cx + rad * Math.cos(angle) + (Math.random() - 0.5) * 20,
        y: cy + rad * Math.sin(angle) + (Math.random() - 0.5) * 20,
        vx: 0, vy: 0,
        r: c.is_abstract ? 8 : 12,
      };
    });

    const idxOf = id => this._nodes.findIndex(n => n.id === id);

    this._edges = [];
    // 继承边
    for (const c of classes) {
      if (c.parent_gid) {
        const si = idxOf(c.gid), ti = idxOf(c.parent_gid);
        if (si >= 0 && ti >= 0) this._edges.push({ s: si, t: ti, label: '', type: 'inherit' });
      }
    }
    // 对象属性边
    for (const r of relations) {
      const si = idxOf(r.domain_class_gid), ti = idxOf(r.range_class_gid);
      if (si >= 0 && ti >= 0) this._edges.push({ s: si, t: ti, label: r.label_zh || r.name, type: 'relation' });
    }

    this._alpha = 1;
    this._startSim();
  }

  setSelected(gid) {
    this._sel = gid;
    this._draw();
    // 平移视口让选中节点居中
    const n = this._nodes.find(n => n.id === gid);
    if (!n) return;
    const W = this._canvas.width, H = this._canvas.height;
    this._tx = W / 2 - n.x * this._scale;
    this._ty = H / 2 - n.y * this._scale;
    this._draw();
  }

  destroy() {
    cancelAnimationFrame(this._raf);
    this._ro?.disconnect();
  }

  // ── 力模拟 ────────────────────────────────────────────────────────────────

  _startSim() {
    cancelAnimationFrame(this._raf);
    const tick = () => {
      this._simStep();
      this._draw();
      if (this._alpha > 0.001) this._raf = requestAnimationFrame(tick);
    };
    this._raf = requestAnimationFrame(tick);
  }

  _simStep() {
    const nodes = this._nodes;
    const edges = this._edges;
    const W = this._canvas.width, H = this._canvas.height;
    const cx = W / 2, cy = H / 2;
    const a  = this._alpha;

    // 排斥
    const KR = 2800;   // 降低排斥 → 节点更近
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const d2 = dx * dx + dy * dy + 1;
        const f  = KR / d2;
        nodes[i].vx += f * dx; nodes[i].vy += f * dy;
        nodes[j].vx -= f * dx; nodes[j].vy -= f * dy;
      }
    }

    // 弹簧 — 缩短边长目标值
    const L_INHERIT  = 55;   // 继承边更短
    const L_RELATION = 75;   // 关系边也更短
    const KS = 0.10;         // 弹力更强
    for (const e of edges) {
      const ni = nodes[e.s], nj = nodes[e.t];
      if (!ni || !nj) continue;
      const dx = nj.x - ni.x, dy = nj.y - ni.y;
      const d  = Math.sqrt(dx * dx + dy * dy) || 1;
      const L  = e.type === 'inherit' ? L_INHERIT : L_RELATION;
      const f  = KS * (d - L);
      const fx = f * dx / d, fy = f * dy / d;
      ni.vx += fx; ni.vy += fy;
      nj.vx -= fx; nj.vy -= fy;
    }

    // 向心
    const KC = 0.012;
    for (const n of nodes) {
      n.vx += (cx - n.x) * KC;
      n.vy += (cy - n.y) * KC;
    }

    // 应用速度 + 阻尼
    const damp = 0.82;
    for (const n of nodes) {
      if (n._pinned) continue;
      n.vx *= damp; n.vy *= damp;
      n.x  += n.vx * a; n.y += n.vy * a;
    }

    this._alpha *= 0.97;
  }

  // ── 绘制 ─────────────────────────────────────────────────────────────────

  _draw() {
    const cv = this._canvas, ctx = this._ctx;
    const W = cv.width, H = cv.height;

    const theme = document.documentElement.getAttribute('data-theme');
    const dark  = theme !== 'light';

    // 明确填充背景色（不依赖透明 canvas）
    ctx.fillStyle = dark ? '#11111b' : '#ffffff';
    ctx.fillRect(0, 0, W, H);

    ctx.save();
    ctx.translate(this._tx, this._ty);
    ctx.scale(this._scale, this._scale);

    // 点阵背景（比线条更轻盈）
    const gs = 28;
    const ox = (((-this._tx / this._scale) % gs) + gs) % gs;
    const oy = (((-this._ty / this._scale) % gs) + gs) % gs;
    ctx.fillStyle = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.07)';
    for (let x = ox; x < W / this._scale + gs; x += gs) {
      for (let y = oy; y < H / this._scale + gs; y += gs) {
        ctx.beginPath(); ctx.arc(x, y, 1, 0, Math.PI * 2); ctx.fill();
      }
    }

    // ── 边 ──────────────────────────────────────────────────────────────────
    for (const e of this._edges) {
      const ni = this._nodes[e.s], nj = this._nodes[e.t];
      if (!ni || !nj) continue;
      const isRel = e.type === 'relation';
      const dx = nj.x - ni.x, dy = nj.y - ni.y;
      const d  = Math.sqrt(dx * dx + dy * dy) || 1;

      // 曲线（关系边稍微弯曲以区分方向）
      const mx = (ni.x + nj.x) / 2, my = (ni.y + nj.y) / 2;
      const bend = isRel ? 18 : 0;
      const cpx = mx - dy / d * bend, cpy = my + dx / d * bend;

      ctx.beginPath();
      if (bend) {
        ctx.moveTo(ni.x, ni.y);
        ctx.quadraticCurveTo(cpx, cpy, nj.x, nj.y);
      } else {
        ctx.moveTo(ni.x, ni.y);
        ctx.lineTo(nj.x, nj.y);
      }
      ctx.strokeStyle = isRel
        ? (dark ? 'rgba(137,180,250,.65)' : 'rgba(59,130,246,.6)')
        : (dark ? 'rgba(166,227,161,.55)' : 'rgba(22,163,74,.5)');
      ctx.lineWidth   = isRel ? 1.5 : 1.2;
      ctx.setLineDash(isRel ? [5, 3] : []);
      ctx.stroke();
      ctx.setLineDash([]);

      // 箭头（贴着目标节点）
      const r   = nj.r + (nj.id === this._sel ? 4 : 0) + 3;
      // 曲线末点方向
      const tx2 = bend ? (nj.x - cpx) : dx;
      const ty2 = bend ? (nj.y - cpy) : dy;
      const td  = Math.sqrt(tx2 * tx2 + ty2 * ty2) || 1;
      const ax  = nj.x - tx2 / td * r;
      const ay  = nj.y - ty2 / td * r;
      const ang = Math.atan2(ty2, tx2);

      ctx.save();
      ctx.translate(ax, ay);
      ctx.rotate(ang);
      ctx.beginPath();
      ctx.moveTo(0, 0); ctx.lineTo(-9, -4); ctx.lineTo(-9, 4);
      ctx.closePath();
      ctx.fillStyle = isRel
        ? (dark ? 'rgba(137,180,250,.85)' : 'rgba(59,130,246,.8)')
        : (dark ? 'rgba(166,227,161,.75)' : 'rgba(22,163,74,.65)');
      ctx.fill();
      ctx.restore();

      // 关系标签（带背景胶囊）
      if (isRel && e.label) {
        ctx.save();
        ctx.font = 'bold 9px -apple-system,sans-serif';
        const tw = ctx.measureText(e.label).width;
        const lx = bend ? cpx : mx;
        const ly = bend ? cpy - 4 : my - 4;
        // 胶囊背景
        const pad = 3;
        ctx.fillStyle = dark ? 'rgba(30,30,46,.85)' : 'rgba(255,255,255,.9)';
        ctx.beginPath();
        const bx = lx - tw / 2 - pad, by = ly - 9;
        const bw = tw + pad * 2, bh = 11;
        ctx.roundRect?.(bx, by, bw, bh, 3) || ctx.rect(bx, by, bw, bh);
        ctx.fill();
        ctx.fillStyle = dark ? 'rgba(137,180,250,.9)' : 'rgba(37,99,235,.85)';
        ctx.textAlign = 'center';
        ctx.fillText(e.label, lx, ly);
        ctx.restore();
      }
    }

    // ── 节点 ─────────────────────────────────────────────────────────────────
    for (const n of this._nodes) {
      const isSel = n.id === this._sel;
      const r = n.r + (isSel ? 4 : 0);

      // 选中光晕
      if (isSel) {
        const grad = ctx.createRadialGradient(n.x, n.y, r, n.x, n.y, r + 10);
        grad.addColorStop(0, 'rgba(249,226,175,.35)');
        grad.addColorStop(1, 'rgba(249,226,175,0)');
        ctx.beginPath(); ctx.arc(n.x, n.y, r + 10, 0, Math.PI * 2);
        ctx.fillStyle = grad; ctx.fill();
      }

      // 节点圆（填充 + 描边）
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2);

      if (n.abstract) {
        // 抽象类：白/深色填充 + 彩色描边
        ctx.fillStyle   = dark ? 'rgba(17,17,27,.8)' : 'rgba(255,255,255,.9)';
        ctx.strokeStyle = isSel ? '#f9e2af' : n.color;
        ctx.lineWidth   = isSel ? 2.5 : 2;
        ctx.setLineDash([4, 2]);
      } else {
        // 具体类：彩色填充
        ctx.fillStyle   = isSel ? '#f9e2af' : n.color;
        ctx.strokeStyle = dark ? 'rgba(255,255,255,.3)' : 'rgba(0,0,0,.2)';
        ctx.lineWidth   = isSel ? 2.5 : 1.5;
      }
      ctx.fill(); ctx.stroke();
      ctx.setLineDash([]);

      // 节点标签
      const textY = n.y + r + 12;
      ctx.font = `${isSel ? 'bold ' : ''}10px -apple-system,sans-serif`;
      const tw  = ctx.measureText(n.label).width;
      // 标签背景
      ctx.fillStyle = dark ? 'rgba(17,17,27,.8)' : 'rgba(255,255,255,.85)';
      const lpad = 3;
      ctx.beginPath();
      ctx.roundRect?.(n.x - tw / 2 - lpad, textY - 10, tw + lpad * 2, 12, 3)
        || ctx.rect(n.x - tw / 2 - lpad, textY - 10, tw + lpad * 2, 12);
      ctx.fill();
      // 标签文字
      ctx.textAlign = 'center';
      ctx.fillStyle = isSel ? '#f9e2af'
        : (n.abstract
          ? (dark ? 'rgba(205,214,244,.7)' : 'rgba(52,64,84,.65)')
          : (dark ? '#cdd6f4' : '#1e293b'));
      ctx.fillText(n.label, n.x, textY);
    }

    ctx.restore();
  }

  // ── 事件 ─────────────────────────────────────────────────────────────────

  _worldPt(ex, ey) {
    const r = this._canvas.getBoundingClientRect();
    return {
      x: (ex - r.left - this._tx) / this._scale,
      y: (ey - r.top  - this._ty) / this._scale,
    };
  }

  _hitNode(wx, wy) {
    for (let i = this._nodes.length - 1; i >= 0; i--) {
      const n  = this._nodes[i];
      const r  = n.r + (n.id === this._sel ? 4 : 0) + 4;
      const dx = n.x - wx, dy = n.y - wy;
      if (dx * dx + dy * dy <= r * r) return i;
    }
    return -1;
  }

  _bindEvents() {
    const cv = this._canvas;

    cv.addEventListener('mousedown', e => {
      if (e.button === 1 || e.button === 2) return;
      const { x, y } = this._worldPt(e.clientX, e.clientY);
      const ni = this._hitNode(x, y);
      if (ni >= 0) {
        this._drag = { ni, ox: x - this._nodes[ni].x, oy: y - this._nodes[ni].y };
        this._nodes[ni]._pinned = true;
      } else {
        this._pan = { sx: e.clientX, sy: e.clientY, tx0: this._tx, ty0: this._ty };
      }
    });

    cv.addEventListener('mousemove', e => {
      if (this._drag) {
        const { x, y } = this._worldPt(e.clientX, e.clientY);
        const n = this._nodes[this._drag.ni];
        n.x = x - this._drag.ox; n.y = y - this._drag.oy;
        n.vx = 0; n.vy = 0;
        this._draw();
      } else if (this._pan) {
        this._tx = this._pan.tx0 + (e.clientX - this._pan.sx);
        this._ty = this._pan.ty0 + (e.clientY - this._pan.sy);
        this._draw();
      }
    });

    const end = () => {
      if (this._drag) { this._nodes[this._drag.ni]._pinned = false; this._drag = null; }
      this._pan = null;
    };
    cv.addEventListener('mouseup', end);
    cv.addEventListener('mouseleave', end);

    cv.addEventListener('click', e => {
      if (this._drag) return;
      const { x, y } = this._worldPt(e.clientX, e.clientY);
      const ni = this._hitNode(x, y);
      if (ni >= 0 && this._onClick) this._onClick(this._nodes[ni].id);
    });

    cv.addEventListener('wheel', e => {
      e.preventDefault();
      const r   = cv.getBoundingClientRect();
      const mx  = e.clientX - r.left, my = e.clientY - r.top;
      const ds  = e.deltaY > 0 ? 0.88 : 1.14;
      const ns  = Math.max(0.2, Math.min(4, this._scale * ds));
      this._tx  = mx - (mx - this._tx) * (ns / this._scale);
      this._ty  = my - (my - this._ty) * (ns / this._scale);
      this._scale = ns;
      this._draw();
    }, { passive: false });

    // 双击重置视图
    cv.addEventListener('dblclick', e => {
      const ni = this._hitNode(...Object.values(this._worldPt(e.clientX, e.clientY)));
      if (ni < 0) { this._tx = 0; this._ty = 0; this._scale = 1; this._draw(); }
    });
  }

  _watchResize() {
    this._ro = new ResizeObserver(() => {
      const p = this._canvas.parentElement;
      this._canvas.width  = p.clientWidth;
      this._canvas.height = p.clientHeight;
      this._draw();
    });
    this._ro.observe(this._canvas.parentElement);
  }
}
