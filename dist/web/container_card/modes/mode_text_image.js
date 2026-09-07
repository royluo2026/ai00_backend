'use strict';
/**
 * mode_text_image.js — 图文模式（双栏：左侧可编辑字段详情，右侧附件图片）
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   item_type  : 'task' | 'issue' | 'knowledge' | 'rule'
 *   gid        : 条目 GID
 *   source     : 'cloud' | 'local'
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['text_image'] = (() => {

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── 加载数据（复用 row_detail 逻辑）─────────────────────────────────────
  async function _load(itemType, gid, source, _cloudFetch) {
    if (!_cloudFetch) throw new Error('未连接云端');
    let res;
    if (itemType === 'task') res = await _cloudFetch(`/api/tasks/${gid}`, { method: 'GET' });
    else if (itemType === 'issue') res = await _cloudFetch(`/api/issues/${gid}`, { method: 'GET' });
    else if (itemType === 'knowledge') res = await (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient).call('knowledge.get', { gid });
    else if (itemType === 'rule') res = await _cloudFetch(`/api/rules/${gid}`, { method: 'GET' });
    else throw new Error(`不支持的条目类型: ${itemType}`);
    return res?.data || res || null;
  }

  // ── 渲染 ─────────────────────────────────────────────────────────────────

  function _buildView(containerEl, data, itemType, isCard) {
    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;height:100%;overflow:hidden;';

    // 文字区
    const textPane = document.createElement('div');
    textPane.style.cssText = 'flex:1;overflow-y:auto;padding:12px 16px;border-right:1px solid var(--cc-border,#dcdcdc);';

    // 基本字段
    const FIELDS = [
      { key: 'title',       label: '标题'   },
      { key: 'status',      label: '状态'   },
      { key: 'priority',    label: '优先级' },
      { key: 'description', label: '描述'   },
      { key: 'due_date',    label: '截止'   },
      { key: 'severity',    label: '严重程度'},
    ];

    FIELDS.forEach(f => {
      const v = data[f.key];
      if (v == null || v === '') return;
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:8px;align-items:flex-start;margin-bottom:8px;font-size:13px;';
      row.innerHTML = `
        <span style="color:var(--cc-muted,#6e6e6e);white-space:nowrap;min-width:60px;font-weight:500;font-size:12px;">${_esc(f.label)}</span>
        <span style="color:var(--cc-text,#2e2e2e);word-break:break-word;">${_esc(String(v).slice(0, 200))}${String(v).length > 200 ? '…' : ''}</span>
      `;
      textPane.appendChild(row);
    });

    // 如果没有非图片附件，跳过附件列表
    const nonImageAttach = (data.attachments || []).filter(a => {
      const url = a.url || '';
      return !/\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(url) && a.type !== 'image';
    });

    if (nonImageAttach.length) {
      const section = document.createElement('div');
      section.style.cssText = 'margin-top:8px;padding-top:8px;border-top:1px solid var(--cc-border,#dcdcdc);';
      section.innerHTML = `<div style="font-size:11px;color:var(--cc-muted,#6e6e6e);margin-bottom:4px;">链接附件</div>`;
      nonImageAttach.forEach(a => {
        const chip = document.createElement('div');
        chip.style.cssText = 'display:flex;align-items:center;gap:6px;padding:4px 0;font-size:12px;color:var(--cc-text,#2e2e2e);cursor:pointer;';
        chip.innerHTML = `<svg width="12" height="12" style="flex-shrink:0"><use href="#icon-package"/></svg> ${_esc(a.name || a.url)}`;
        chip.addEventListener('click', () => {
          const url = a.url || '';
          if (a.type === 'file') {
            (window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI)?.openPath?.(url);
          } else {
            (window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI)?.openExternal?.(url)
              || window.open(url, '_blank');
          }
        });
        section.appendChild(chip);
      });
      textPane.appendChild(section);
    }

    // 展开按钮（卡片模式）
    if (isCard) {
      const expandBtn = document.createElement('button');
      expandBtn.style.cssText = 'width:100%;padding:6px;text-align:center;font-size:11px;color:var(--cc-accent,#7b61ff);background:none;border:none;border-top:1px solid var(--cc-border,#dcdcdc);cursor:pointer;margin-top:8px;';
      expandBtn.textContent = '展开全部 →';
      expandBtn.addEventListener('click', () => {
        const parent = window.parent;
        if (parent?.TabManager) {
          parent.TabManager.open('container_card', {
            mode: 'text_image',
            item_type: itemType,
            gid: data.gid,
            source: data._source || 'local',
            title: data.title || '条目详情',
          });
        }
      });
      textPane.appendChild(expandBtn);
    }

    containerEl.appendChild(textPane);

    // 图片区
    const imgAttach = (data.attachments || []).filter(a => {
      const url = a.url || a.path || '';
      return /\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(url) || a.type === 'image';
    });

    if (imgAttach.length > 0) {
      const imgPane = document.createElement('div');
      imgPane.style.cssText = 'width:160px;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:8px;flex-shrink:0;';

      imgAttach.forEach(a => {
        const img = document.createElement('img');
        img.src = a.url || a.path || '';
        img.alt = a.name || '';
        img.style.cssText = 'width:100%;border-radius:4px;border:1px solid var(--cc-border,#dcdcdc);object-fit:cover;cursor:pointer;';
        img.addEventListener('click', () => {
          // 点击图片 → 打开 image_gallery 全屏
          const b64 = btoa(JSON.stringify(imgAttach));
          const idx = imgAttach.indexOf(a);
          const parent = window.parent;
          if (parent?.TabManager) {
            parent.TabManager.open('container_card', {
              mode: 'image_gallery',
              attachments: b64,
              annotation_key: `wb:ann:${data.gid}`,
              editable: 'true',
              title: '图片预览',
            });
          }
        });
        imgPane.appendChild(img);
      });

      containerEl.appendChild(imgPane);
    }
  }

  // ── renderInCard ─────────────────────────────────────────────────────────

  function renderInCard(containerEl, params, ctx) {
    const { item_type = 'task', gid, source = 'local' } = params || {};
    const cloudFetch = ctx?.cloudFetch || window.parent?._cloudFetch || window._cloudFetch || null;

    if (!gid) {
      containerEl.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--cc-muted,#6e6e6e)">未指定条目</div>';
      return () => {};
    }

    containerEl.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--cc-muted,#6e6e6e)">加载中…</div>';
    let destroyed = false;

    _load(item_type, gid, source, cloudFetch).then(data => {
      if (destroyed || !data) return;
      _buildView(containerEl, data, item_type, true);
    }).catch(e => {
      if (!destroyed) containerEl.innerHTML = `<div style="padding:12px;font-size:12px;color:var(--cc-muted)">加载失败: ${_esc(String(e))}</div>`;
    });

    return () => { destroyed = true; };
  }

  // ── renderFullPage ───────────────────────────────────────────────────────

  function renderFullPage(containerEl, urlParams) {
    const item_type  = urlParams.get('item_type') || 'task';
    const gid        = urlParams.get('gid');
    const source     = urlParams.get('source') || 'local';
    const cloudFetch = window._cloudFetch || window.parent?._cloudFetch || null;

    if (!gid) { containerEl.innerHTML = '<div class="cc-empty">未指定条目 GID</div>'; return; }

    containerEl.innerHTML = '<div class="cc-loading">加载中…</div>';

    _load(item_type, gid, source, cloudFetch).then(data => {
      if (!data) { containerEl.innerHTML = '<div class="cc-empty">未找到条目</div>'; return; }
      _buildView(containerEl, data, item_type, false);

      const titleEl = document.getElementById('ccTitle');
      if (titleEl) titleEl.textContent = data.title || '条目详情';
    }).catch(e => {
      containerEl.innerHTML = `<div class="cc-empty">加载失败: ${_esc(String(e))}</div>`;
    });
  }

  return { renderInCard, renderFullPage };
})();
