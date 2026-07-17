'use strict';
/**
 * lv_utils.js  —  BOP / GBOP Lineage 公共工具函数
 *
 * 在 lineage_view/index.html 和 gbop_lineage/index.html 中均需在
 * 各自的 lineage.js 之前加载本文件。
 *
 * 本文件只含纯 DOM 工具函数，无全局状态依赖。
 */

// ── HTML 转义 ─────────────────────────────────────────────────────────

function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── 内联对话框（Electron 兼容，替代 prompt/confirm）─────────────────

function _promptText(message, { nodeTypes = null } = {}) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'lv-dialog-overlay';
    const typeHtml = nodeTypes && nodeTypes.length
      ? `<select class="lv-dialog-select" id="_dlgNodeType">
          ${nodeTypes.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}
        </select>`
      : '';
    overlay.innerHTML = `<div class="lv-dialog-box">
      <div class="lv-dialog-msg">${message}</div>
      ${typeHtml}
      <input class="lv-dialog-input" id="_dlgInput" type="text" placeholder="节点名称…">
      <div class="lv-dialog-btns">
        <button class="lv-btn lv-btn-sm" id="_dlgCancel">取消</button>
        <button class="lv-btn lv-btn-sm" id="_dlgOk"
          style="border-color:var(--blue,#89b4fa);color:var(--blue,#89b4fa)">确认</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    const input = overlay.querySelector('#_dlgInput');
    const typeSelect = overlay.querySelector('#_dlgNodeType');
    input.focus();

    function done(val) { overlay.remove(); resolve(val); }

    overlay.querySelector('#_dlgOk').addEventListener('click', () => {
      const t = input.value.trim();
      if (!t) { input.focus(); return; }
      done({ title: t, nodeType: typeSelect?.value || null });
    });
    overlay.querySelector('#_dlgCancel').addEventListener('click', () => done(null));
    overlay.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const t = input.value.trim();
        if (!t) { input.focus(); return; }
        done({ title: t, nodeType: typeSelect?.value || null });
      }
      if (e.key === 'Escape') done(null);
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) done(null); });
  });
}

function _confirmDialog(message) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'lv-dialog-overlay';
    overlay.innerHTML = `<div class="lv-dialog-box">
      <div class="lv-dialog-msg">${message}</div>
      <div class="lv-dialog-btns">
        <button class="lv-btn lv-btn-sm" id="_dlgCancel">取消</button>
        <button class="lv-btn lv-btn-sm" id="_dlgOk"
          style="border-color:var(--red,#f38ba8);color:var(--red,#f38ba8)">确认删除</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    function done(val) { overlay.remove(); resolve(val); }
    overlay.querySelector('#_dlgOk').addEventListener('click', () => done(true));
    overlay.querySelector('#_dlgCancel').addEventListener('click', () => done(false));
    overlay.addEventListener('keydown', e => {
      if (e.key === 'Enter') done(true);
      if (e.key === 'Escape') done(false);
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) done(false); });
  });
}

// ── 图片灯箱（两级交互：网格总览 → 单张全屏）──────────────────────

/** 图片灯箱：传入 img src 数组，支持左右切换 */
function _openImageLightbox(srcs, _startIndex = 0, opts = {}) {
  // opts.onAddMore: 提供时在灯箱底部显示「继续上传/粘贴」按钮
  if (!srcs || !srcs.length) return;

  // 单张图直接进入全屏，无需经过网格
  const multi = srcs.length > 1;

  // ── 根层遮罩 ──────────────────────────────────────────────────
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;';

  // ── 第二层：单张全屏 ──────────────────────────────────────────
  let singleLayer = null;

  const showSingle = (idx) => {
    if (singleLayer) singleLayer.remove();
    singleLayer = document.createElement('div');
    singleLayer.style.cssText = 'position:absolute;inset:0;background:rgba(0,0,0,0.88);display:flex;align-items:center;justify-content:center;cursor:zoom-out;z-index:2;';
    const img = document.createElement('img');
    img.style.cssText = 'max-width:92vw;max-height:92vh;border-radius:6px;box-shadow:0 8px 40px rgba(0,0,0,0.6);pointer-events:none;user-select:none;';
    img.src = srcs[idx];
    // ESC 提示
    const hint = document.createElement('div');
    hint.style.cssText = 'position:absolute;bottom:16px;left:50%;transform:translateX(-50%);color:rgba(255,255,255,0.4);font-size:11px;pointer-events:none;';
    hint.textContent = multi ? '点击空白返回总览' : '点击空白关闭';
    singleLayer.appendChild(img);
    singleLayer.appendChild(hint);
    // 点击空白区域（非图片）→ 返回网格或关闭
    singleLayer.addEventListener('click', () => {
      singleLayer.remove();
      singleLayer = null;
      if (!multi) closeAll();
    });
    overlay.appendChild(singleLayer);
  };

  // ── 第一层：网格总览（多图才有） ──────────────────────────────
  if (multi) {
    // 列数：≤2张各占一列；≥3张用 ceil(n/2) 列，保证最多两行
    const cols = srcs.length <= 2 ? srcs.length : Math.ceil(srcs.length / 2);
    const rows = Math.ceil(srcs.length / cols);
    const maxH = rows === 1 ? '72vh' : rows === 2 ? '42vh' : '28vh';
    // 用 flexbox + justify-content:center，最后一行不满时自动居中
    const itemBasis = `calc(${(100 / cols).toFixed(2)}% - 14px)`;
    const gridWrap = document.createElement('div');
    gridWrap.style.cssText = `position:relative;z-index:1;display:flex;flex-wrap:wrap;justify-content:center;gap:14px;max-width:92vw;max-height:94vh;overflow:auto;padding:20px;cursor:default;`;

    srcs.forEach((src, i) => {
      const cell = document.createElement('div');
      cell.style.cssText = `flex:0 0 ${itemBasis};border-radius:8px;overflow:hidden;cursor:zoom-in;transition:transform 0.15s,box-shadow 0.15s;box-shadow:0 2px 12px rgba(0,0,0,0.5);`;
      const img = document.createElement('img');
      img.style.cssText = `display:block;width:100%;max-height:${maxH};object-fit:contain;`;
      img.src = src;
      img.onerror = () => { cell.style.display = 'none'; };
      cell.appendChild(img);
      cell.addEventListener('mouseenter', () => { cell.style.transform = 'scale(1.02)'; cell.style.boxShadow = '0 6px 24px rgba(0,0,0,0.7)'; });
      cell.addEventListener('mouseleave', () => { cell.style.transform = ''; cell.style.boxShadow = '0 2px 12px rgba(0,0,0,0.5)'; });
      cell.addEventListener('click', e => { e.stopPropagation(); showSingle(i); });
      gridWrap.appendChild(cell);
    });

    // 点击空白（gridWrap 以外）→ 关闭
    overlay.addEventListener('click', e => {
      if (!singleLayer && e.target === overlay) closeAll();
    });
    overlay.appendChild(gridWrap);
  } else {
    // 单张直接进全屏
    showSingle(0);
  }

  const closeAll = () => {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
  };

  const onKey = e => {
    if (e.key === 'Escape') {
      if (singleLayer) { singleLayer.remove(); singleLayer = null; if (!multi) closeAll(); }
      else closeAll();
    }
  };

  document.addEventListener('keydown', onKey);

  // 「继续上传/粘贴」按钮（可选）
  if (opts.onAddMore) {
    const addBtn = document.createElement('button');
    addBtn.style.cssText =
      'position:absolute;bottom:20px;right:24px;z-index:10;' +
      'padding:6px 14px;font-size:12px;border-radius:5px;cursor:pointer;' +
      'background:rgba(49,50,68,0.9);color:#cdd6f4;border:1px solid #585b70;' +
      'transition:background .1s;';
    addBtn.textContent = '＋ 继续上传 / 粘贴';
    addBtn.addEventListener('mouseenter', () => addBtn.style.background = 'rgba(137,180,250,0.2)');
    addBtn.addEventListener('mouseleave', () => addBtn.style.background = 'rgba(49,50,68,0.9)');
    addBtn.addEventListener('click', e => {
      e.stopPropagation();
      closeAll();
      opts.onAddMore();
    });
    overlay.appendChild(addBtn);
  }

  document.body.appendChild(overlay);
}
