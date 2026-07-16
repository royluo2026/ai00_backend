'use strict';
/**
 * mode_image_gallery.js — 多图预览 + SVG 标注
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   attachments      : base64(JSON) — [{name, url, type}]
 *   annotation_key   : localStorage key，用于持久化标注
 *   editable         : 'true' | 'false'
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['image_gallery'] = (() => {

  // 预设颜色
  const PRESET_COLORS = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c'];
  const ANN_TOOLS = ['select', 'rect', 'circle', 'line', 'arrow', 'text'];
  const ANN_TOOL_LABELS = { select: '选择', rect: '矩形', circle: '圆形', line: '直线', arrow: '箭头', text: '文字' };

  // ── 标注持久化（DB）─────────────────────────────────────────────────────────
  async function _loadAnn(key) {
    if (!key) return {};
    try {
      const cf = window.parent?._cloudFetch || window._cloudFetch;
      if (cf) {
        const resp = await cf(`/api/annotations/${encodeURIComponent(key)}`);
        if (resp?.data) return resp.data;
      }
    } catch (_) {}
    // fallback: localStorage
    try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch { return {}; }
  }

  async function _saveAnn(key, data) {
    if (!key) return;
    // 本地 localStorage 作为即时写入（UI响应）
    try { localStorage.setItem(key, JSON.stringify(data)); } catch (_) {}
    // 异步持久化到 DB
    try {
      const cf = window.parent?._cloudFetch || window._cloudFetch;
      if (cf) {
        await cf(`/api/annotations/${encodeURIComponent(key)}`, {
          method: 'PUT',
          body: JSON.stringify({ data }),
        });
      }
    } catch (_) {}
  }

  // ── 解析 attachments ──────────────────────────────────────────────────────
  function _parseAttachments(b64) {
    if (!b64) return [];
    try {
      // UTF-8 安全解码（兼容 AttachmentsWidget._b64EncUtf8 编码的中文文件名）
      let json;
      try {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        json = new TextDecoder().decode(bytes);
      } catch (_) {
        json = atob(b64); // fallback：旧版 ASCII-only 数据
      }
      const arr  = JSON.parse(json);
      // 只保留图片（URL 扩展名 或 mime 字段判断）
      return arr.filter(a => {
        if (!a.url && !a.path) return false;
        const url = a.url || a.path || '';
        return /\.(png|jpe?g|gif|webp|svg|bmp|tiff?|heic|avif|jfif)$/i.test(url)
          || (a.mime || '').startsWith('image/')
          || a.type === 'image';
      });
    } catch { return []; }
  }

  // ── 主渲染逻辑 ────────────────────────────────────────────────────────────
  async function _build(containerEl, images, annKey, editable, isCard, startIdx) {
    containerEl.innerHTML = '';

    if (!images.length) {
      containerEl.innerHTML = '<div class="cc-empty">暂无图片</div>';
      return null;
    }

    // annKey 未传时，用图片 URL 派生一个（保证同一批图片的标注可持久化）
    if (!annKey && images.length) {
      annKey = 'img_ann_' + btoa(encodeURIComponent(images[0].url || images[0].path || '')).slice(0, 32);
    }

    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    let currentIdx = (typeof startIdx === 'number' && startIdx >= 0 && startIdx < images.length) ? startIdx : 0;
    let annData    = await _loadAnn(annKey);  // { [idx]: shapes[] }
    let dp         = null;              // DrawPrimitives 实例

    // 保存当前标注到持久化
    function _doSave(btn) {
      if (dp) annData[currentIdx] = dp.toJSON() || [];
      _saveAnn(annKey, annData);
      if (btn) { btn.textContent = '已保存'; setTimeout(() => { btn.textContent = '保存标注'; }, 1200); }
    }

    // ── 标注工具栏（仅全屏 + editable）──
    let annToolbar = null;
    if (editable && !isCard) {
      annToolbar = document.createElement('div');
      annToolbar.className = 'cc-ann-toolbar';
      annToolbar.style.cssText = 'display:flex;align-items:center;gap:6px;padding:4px 10px;background:var(--cc-bg,#fff);border-bottom:1px solid var(--cc-border,#dcdcdc);flex-shrink:0;flex-wrap:wrap;';

      // 工具按钮
      ANN_TOOLS.forEach(tool => {
        const btn = document.createElement('button');
        btn.className = 'cc-ann-tool-btn' + (tool === 'select' ? ' active' : '');
        btn.dataset.tool = tool;
        btn.textContent = ANN_TOOL_LABELS[tool];
        btn.addEventListener('click', () => {
          annToolbar.querySelectorAll('.cc-ann-tool-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          dp?.setTool(tool);
        });
        annToolbar.appendChild(btn);
      });

      // 分隔
      const sep = document.createElement('span');
      sep.style.cssText = 'width:1px;height:16px;background:var(--cc-border,#dcdcdc);flex-shrink:0;';
      annToolbar.appendChild(sep);

      // 颜色点
      PRESET_COLORS.forEach((color, i) => {
        const dot = document.createElement('div');
        dot.className = 'cc-ann-color-dot' + (i === 0 ? ' active' : '');
        dot.style.cssText = `width:16px;height:16px;border-radius:50%;background:${color};border:2px solid var(--cc-border,#dcdcdc);cursor:pointer;flex-shrink:0;`;
        dot.dataset.color = color;
        dot.addEventListener('click', () => {
          annToolbar.querySelectorAll('.cc-ann-color-dot').forEach(d => d.classList.remove('active'));
          dot.classList.add('active');
          dp?.setColor(color);
        });
        annToolbar.appendChild(dot);
      });

      // 自定义颜色
      const colorInput = document.createElement('input');
      colorInput.type = 'color';
      colorInput.value = '#e74c3c';
      colorInput.style.cssText = 'width:22px;height:22px;border:none;background:none;cursor:pointer;padding:0;';
      colorInput.title = '自定义颜色';
      colorInput.addEventListener('change', () => {
        annToolbar.querySelectorAll('.cc-ann-color-dot').forEach(d => d.classList.remove('active'));
        dp?.setColor(colorInput.value);
      });
      annToolbar.appendChild(colorInput);

      const saveBtn = document.createElement('button');
      saveBtn.className = 'cc-ann-tool-btn';
      saveBtn.textContent = '保存标注';
      saveBtn.style.cssText = 'margin-left:auto;';
      saveBtn.addEventListener('click', () => _doSave(saveBtn));
      annToolbar.appendChild(saveBtn);

      const clearBtn = document.createElement('button');
      clearBtn.className = 'cc-ann-tool-btn';
      clearBtn.textContent = '清除';
      clearBtn.style.cssText = 'color:var(--color-danger,#f38ba8);';
      clearBtn.addEventListener('click', () => {
        dp?.clearAll?.();
        annData[currentIdx] = [];
        _saveAnn(annKey, annData);
      });
      annToolbar.appendChild(clearBtn);

      containerEl.appendChild(annToolbar);
    }

    // ── 图片查看区 ──
    const viewerEl = document.createElement('div');
    viewerEl.className = 'cc-gallery-viewer';
    viewerEl.style.cssText = 'flex:1;min-height:0;position:relative;overflow:hidden;background:#000;';

    const imgEl = document.createElement('img');
    imgEl.className = 'cc-gallery-img';
    imgEl.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:block;pointer-events:none;user-select:none;';
    imgEl.onerror = () => {
      imgEl.style.display = 'none';
      const errEl = viewerEl.querySelector('.cc-img-err') || document.createElement('div');
      errEl.className = 'cc-img-err';
      errEl.style.cssText = 'color:var(--cc-muted,#999);font-size:12px;text-align:center;padding:20px;';
      errEl.textContent = '图片加载失败：' + (imgEl.dataset.name || imgEl.src);
      if (!viewerEl.querySelector('.cc-img-err')) viewerEl.appendChild(errEl);
    };
    imgEl.onload = () => {
      imgEl.style.display = '';
      const errEl = viewerEl.querySelector('.cc-img-err');
      if (errEl) errEl.remove();
    };
    viewerEl.appendChild(imgEl);

    // SVG 标注层
    const svgEl = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svgEl.setAttribute('class', 'cc-gallery-svg');
    svgEl.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;overflow:visible;';
    viewerEl.appendChild(svgEl);

    containerEl.appendChild(viewerEl);

    // ── 底部导航栏 ──
    const navEl = document.createElement('div');
    navEl.className = 'cc-gallery-nav';
    navEl.style.cssText = 'height:44px;background:var(--cc-bg,#fff);border-top:1px solid var(--cc-border,#dcdcdc);display:flex;align-items:center;justify-content:center;gap:12px;flex-shrink:0;';

    const prevBtn = document.createElement('button');
    prevBtn.className = 'cc-gallery-nav-btn';
    prevBtn.innerHTML = '&#8592;';
    prevBtn.style.cssText = 'display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;border:1px solid var(--cc-border,#dcdcdc);background:var(--cc-bg2,#f7f6f3);color:var(--cc-text,#2e2e2e);cursor:pointer;font-size:14px;';

    const counter = document.createElement('span');
    counter.className = 'cc-gallery-counter';
    counter.style.cssText = 'font-size:12px;color:var(--cc-muted,#6e6e6e);min-width:50px;text-align:center;';

    const nextBtn = document.createElement('button');
    nextBtn.className = 'cc-gallery-nav-btn';
    nextBtn.innerHTML = '&#8594;';
    nextBtn.style.cssText = prevBtn.style.cssText;

    navEl.appendChild(prevBtn);
    navEl.appendChild(counter);
    navEl.appendChild(nextBtn);

    if (!isCard) containerEl.appendChild(navEl);

    // ── 图片切换 ──
    function _showImage(idx) {
      // 保存当前标注
      if (dp) {
        annData[currentIdx] = dp.toJSON() || [];
        _saveAnn(annKey, annData);
      }

      currentIdx = Math.max(0, Math.min(idx, images.length - 1));
      const img = images[currentIdx];
      const src = img.url || img.path || '';
      console.log('[mode_image_gallery] loading image src:', src);
      imgEl.style.display = '';
      imgEl.dataset.name = img.name || '';
      imgEl.alt = img.name || '';

      imgEl.src = src;

      counter.textContent = `${currentIdx + 1} / ${images.length}`;
      prevBtn.disabled = currentIdx === 0;
      nextBtn.disabled = currentIdx === images.length - 1;

      // 初始化 DrawPrimitives
      svgEl.innerHTML = '';
      if (window.DrawPrimitives && editable && !isCard) {
        dp = new DrawPrimitives(svgEl, { editable: true });
        // 恢复标注
        const saved = annData[currentIdx] || [];
        if (saved.length) dp.fromJSON(saved);
        // 监听变化
        dp.onChange(shapes => {
          annData[currentIdx] = shapes;
          _saveAnn(annKey, annData);
        });
      } else {
        dp = null;
        // 只读：绘制已有标注（非 editable DrawPrimitives）
        if (window.DrawPrimitives && !isCard) {
          dp = new DrawPrimitives(svgEl, { editable: false });
          const saved = annData[currentIdx] || [];
          if (saved.length) dp.fromJSON(saved);
        }
      }
    }

    prevBtn.addEventListener('click', () => _showImage(currentIdx - 1));
    nextBtn.addEventListener('click', () => _showImage(currentIdx + 1));

    // 键盘导航（全屏模式）
    if (!isCard) {
      const onKey = e => {
        if (e.key === 'ArrowLeft')  { e.preventDefault(); _showImage(currentIdx - 1); }
        if (e.key === 'ArrowRight') { e.preventDefault(); _showImage(currentIdx + 1); }
      };
      document.addEventListener('keydown', onKey);
      // 返回清理函数
      containerEl._galleryKeyCleanup = () => document.removeEventListener('keydown', onKey);
    }

    _showImage(0);
    return { goTo: _showImage };
  }

  // ── renderInCard ─────────────────────────────────────────────────────────

  function renderInCard(containerEl, params, ctx) {
    const annKey   = params?.annotation_key || null;
    const images   = _parseAttachments(params?.attachments)
                   || (ctx?.contextData?.attachments ? _parseAttachments(btoa(JSON.stringify(ctx.contextData.attachments))) : []);

    _build(containerEl, images, annKey, false, true);  // async, no await needed (UI will update)

    // 双击弹出全屏
    containerEl.addEventListener('dblclick', () => {
      const parent = window.parent;
      if (!parent?.TabManager) return;
      parent.TabManager.open('container_card', {
        mode: 'image_gallery',
        attachments: params?.attachments,
        annotation_key: annKey,
        editable: 'true',
        title: '图片预览',
      });
    });

    return () => {};
  }

  // ── renderFullPage ───────────────────────────────────────────────────────

  function renderFullPage(containerEl, urlParams) {
    const annKey   = urlParams.get('annotation_key') || null;
    const editable = urlParams.get('editable') !== 'false';
    const rawAttachments = urlParams.get('attachments') || '';
    const startIdx = parseInt(urlParams.get('idx'), 10) || 0;
    console.log('[mode_image_gallery] raw attachments param length:', rawAttachments.length);
    const images   = _parseAttachments(rawAttachments);
    console.log('[mode_image_gallery] parsed images:', images.length, 'startIdx:', startIdx, images.map(i => ({ name: i.name, url: i.url?.substring(0, 50) })));

    _build(containerEl, images, annKey, editable, false, startIdx);

    // 更新标题（优先使用传入的 title，否则用图片数量）
    const titleEl = document.getElementById('ccTitle');
    if (titleEl) {
      const titleParam = urlParams.get('title') || '';
      if (titleParam) {
        try { titleEl.textContent = _b64DecUtf8(titleParam); } catch (_) { titleEl.textContent = titleParam; }
      } else {
        titleEl.textContent = `图片预览 (${images.length})`;
      }
    }
  }

  return { renderInCard, renderFullPage };
})();
