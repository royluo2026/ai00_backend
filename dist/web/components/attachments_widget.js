'use strict';
/**
 * AttachmentsWidget — 通用附件组件
 *
 * 用法（在 RDP 字段行中）：
 *   const w = new AttachmentsWidget({
 *     el:        fieldRowEl,
 *     attachments: [],          // [{ name, url, mime }]
 *     isCloud:   false,         // true = 云端上传；false = 本地复制
 *     itemType:  'task',
 *     itemGid:   'xxx',
 *     onSave:    (list) => { ... }  // 附件列表变化时回调
 *   });
 *   w.render();
 *
 * 静态方法（用于 GridEditor cell 渲染）：
 *   AttachmentsWidget.renderCell(val, parent) → HTML 字符串（含 data-att-preview button）
 *   AttachmentsWidget.openPreview(att)    → 打开对应容器卡片预览
 */
class AttachmentsWidget {
  constructor({ el, attachments, isCloud, itemType, itemGid, onSave, readonly }) {
    this._el          = el;
    this._list        = Array.isArray(attachments) ? [...attachments] : [];
    this._isCloud     = !!isCloud;
    this._itemType    = itemType || '';
    this._itemGid     = itemGid  || '';
    this._onSave      = onSave   || null;
    this._uploading   = false;
    this._readonly    = !!readonly;
  }

  // ─── 公开 API ──────────────────────────────────────────────────────────────

  render() {
    this._el.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'att-widget';

    // 已有附件图标
    this._list.forEach((att, idx) => {
      const item = document.createElement('div');
      item.className = 'att-item';
      item.innerHTML = `
        ${AttachmentsWidget._fileIcon(att)}
        <span class="att-item-name" title="${_attEsc(att.name)}">${_attEsc(att.name)}</span>
        ${this._readonly ? '' : `<button class="att-delete-btn" data-idx="${idx}" title="删除">×</button>`}`;
      // 点击图标名称区域 → 预览
      item.addEventListener('click', (e) => {
        if (e.target.closest('.att-delete-btn')) return;
        AttachmentsWidget.openPreview(att, {itemType:this._itemType,itemGid:this._itemGid}).catch(error=>alert('附件读取失败：'+error.message));
      });
      // 删除按钮
      if (!this._readonly) {
        item.querySelector('.att-delete-btn')?.addEventListener('click', (e) => {
          e.stopPropagation();
          this._delete(idx);
        });
      }
      wrap.appendChild(item);
    });

    // 添加按钮（只读模式下隐藏）
    if (!this._readonly) {
      const addBtn = document.createElement('button');
      addBtn.className = 'att-add-btn';
      addBtn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>添加`;
      addBtn.addEventListener('click', () => {
        if (this._uploading) return;
        this._isCloud ? this._uploadCloud() : this._uploadLocal();
      });
      wrap.appendChild(addBtn);
    }

    if (this._uploading) {
      const tip = document.createElement('span');
      tip.className = 'att-uploading';
      tip.textContent = '上传中…';
      wrap.appendChild(tip);
    }

    this._el.appendChild(wrap);
  }

  // ─── 本地上传（Electron IPC）──────────────────────────────────────────────

  async _uploadLocal() {
return this._uploadCloud();
}

  // ─── 云端上传（fetch /api/uploads）──────────────────────────────────────────

  async _uploadCloud() {
this._uploading=true;this.render();
 try{const result=await window.AI00Business.invoke('base.artifact.batch.import',{version:1,payload:{},native_io:{select:'attachment'}});
  for(const item of result.artifacts)this._list.push({name:item.name,mime:item.artifact_ref.media_type,artifact_ref:item.artifact_ref,url:window.AI00Business.artifactPath(item)});
  await this._save();
 }catch(error){if(error.code!=='native_selection_cancelled')alert('上传失败：'+error.message);}
 finally{this._uploading=false;this.render();}
}

  // ─── 删除 ─────────────────────────────────────────────────────────────────

  async _delete(idx) {
    this._list.splice(idx, 1);
    await this._save();
    this.render();
  }

  // ─── 保存 ─────────────────────────────────────────────────────────────────

  async _save() {
    this._list=await Promise.all(this._list.map(async att=>{
      const file=await window.AI00Business.resolveArtifactPath(await window.AI00Business.attachmentPath(att,{itemType:this._itemType,itemGid:this._itemGid}));
      return {name:file.name,mime:file.artifact_ref.media_type,artifact_ref:file.artifact_ref,url:window.AI00Business.artifactPath(file)};
    }));
    if (this._onSave) return this._onSave([...this._list]);
  }

  // ─── 静态工具方法 ─────────────────────────────────────────────────────────

  /** 按文件扩展名推断 MIME */
  static _detectMime(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    const map = {
      jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
      gif: 'image/gif',  webp: 'image/webp', svg: 'image/svg+xml',
      pdf: 'application/pdf',
      md: 'text/markdown', markdown: 'text/markdown',
      txt: 'text/plain', json: 'application/json',
      csv: 'text/csv',
      xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      xls: 'application/vnd.ms-excel',
    };
    return map[ext] || 'application/octet-stream';
  }

  /** 返回 SVG 图标字符串，按 mime 区分 */
  static _fileIcon(att) {
    const mime = att.mime || AttachmentsWidget._detectMime(att.name || '');
    if (mime.startsWith('image/')) {
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a6e3a1" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>
        <polyline points="21 15 16 10 5 21"/></svg>`;
    }
    if (mime === 'application/pdf') {
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f38ba8" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <text x="6" y="18" fill="#f38ba8" stroke="none" font-size="5" font-weight="bold">PDF</text></svg>`;
    }
    if (mime.startsWith('text/markdown') || (att.name || '').match(/\.md$/i)) {
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#89b4fa" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/></svg>`;
    }
    if (mime === 'text/csv' || mime.includes('spreadsheetml') || mime === 'application/vnd.ms-excel' ||
        (att.name || '').match(/\.(xlsx?|csv)$/i)) {
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a6e3a1" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>
        <line x1="10" y1="9" x2="14" y2="9"/></svg>`;
    }
    // 通用文件
    return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a6adc8" stroke-width="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/></svg>`;
  }

  /** Grid 单元格 HTML（只读图标列表）*/
  static renderCell(val, parent) {
    let list = [];
    if (!val) return '';
    if (Array.isArray(val)) list = val;
    else { try { list = JSON.parse(val); } catch (_) { return ''; } }
    if (!list.length) return '';

    return `<span class="att-cell">${list.map(att => {
      const safe = _b64EncUtf8(JSON.stringify({attachment:att,parent_ref:{itemType:parent?.itemType,itemGid:parent?.itemGid}}));
      return `<button data-att-preview="${safe}" title="${_attEsc(att.name)}"
                style="background:none;border:none;padding:2px;cursor:pointer;display:inline-flex;border-radius:3px;">
                ${AttachmentsWidget._fileIcon(att)}
              </button>`;
    }).join('')}</span>`;
  }

  /** 在当前页面弹出浮层，iframe 加载 container_card 预览 */
  static _openCardOverlay(mode, queryParams) {
    // 避免重复弹窗
    if (document.querySelector('.att-card-overlay')) return;

    const qs = Object.entries(queryParams)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');

    const overlay = document.createElement('div');
    overlay.className = 'att-card-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;';

    const card = document.createElement('div');
    card.style.cssText = 'width:88vw;height:88vh;max-width:1200px;background:var(--cc-bg,#fff);border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,0.35);display:flex;flex-direction:column;overflow:hidden;position:relative;';

    // 关闭按钮
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.cssText = 'position:absolute;top:8px;right:12px;z-index:1;border:none;background:none;font-size:22px;color:var(--cc-muted,#999);cursor:pointer;line-height:1;padding:4px 8px;border-radius:4px;';
    closeBtn.addEventListener('click', () => overlay.remove());
    closeBtn.addEventListener('mouseenter', () => { closeBtn.style.background = 'var(--cc-border,#dcdcdc)'; });
    closeBtn.addEventListener('mouseleave', () => { closeBtn.style.background = 'none'; });
    card.appendChild(closeBtn);

    // iframe
    const iframe = document.createElement('iframe');
    const src = `../container_card/index.html?mode=${mode}&${qs}`;
    console.log('[AttWidget._openCardOverlay] iframe src:', src);
    iframe.src = src;
    iframe.style.cssText = 'flex:1;border:none;width:100%;';
    iframe.addEventListener('error', (e) => console.error('[AttWidget._openCardOverlay] iframe error:', e));
    card.appendChild(iframe);

    overlay.appendChild(card);

    // 点击遮罩关闭
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });

    // Escape 关闭
    const onKey = (e) => {
      if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); }
    };
    document.addEventListener('keydown', onKey);

    document.body.appendChild(overlay);
  }

  /** 按 mime 路由到容器卡片预览 */
  static async openPreview(att, parent) {
    const file=await window.AI00Business.resolveArtifactPath(await window.AI00Business.attachmentPath(att,parent));
    att={name:file.name,mime:file.artifact_ref.media_type,artifact_ref:file.artifact_ref,url:window.AI00Business.artifactPath(file)};
    if(att.mime.startsWith('image/')||att.mime==='application/pdf'){
      const bytes=await window.AI00Business.invoke('base.artifact.bytes.get',{version:1,payload:{artifact_ref:file.artifact_ref}});
      att.url='data:'+file.artifact_ref.media_type+';base64,'+bytes.data_base64;
    }
    console.log('[AttWidget.openPreview] called with att:', JSON.stringify(att));
    const mime = att.mime || AttachmentsWidget._detectMime(att.name || '');
    console.log('[AttWidget.openPreview] mime:', mime);

    if (mime.startsWith('image/')) {
      const attJson = _b64EncUtf8(JSON.stringify([att]));
      const titleB64 = _b64EncUtf8(att.name);
      AttachmentsWidget._openCardOverlay('image_gallery', { attachments: attJson, title: titleB64 });
      return;
    }

    if (mime === 'application/pdf') {
      const pathB64  = _b64EncUtf8(att.url);
      const titleB64 = _b64EncUtf8(att.name);
      console.log('[AttWidget.openPreview] PDF mode, att.url:', att.url, '→ pathB64:', pathB64);
      AttachmentsWidget._openCardOverlay('pdf', { path: pathB64, title: titleB64 });
      return;
    }

    if (mime.startsWith('text/markdown') || (att.name || '').match(/\.md$/i)) {
      const pathB64  = _b64EncUtf8(att.url);
      const titleB64 = _b64EncUtf8(att.name);
      console.log('[AttWidget.openPreview] Markdown mode, att.url:', att.url, '→ pathB64:', pathB64);
      AttachmentsWidget._openCardOverlay('markdown', { path: pathB64, title: titleB64 });
      return;
    }

    if (mime === 'text/csv' || mime.includes('spreadsheetml') || mime === 'application/vnd.ms-excel' ||
        (att.name || '').match(/\.(xlsx?|csv)$/i)) {
      const pathB64  = _b64EncUtf8(att.url);
      const titleB64 = _b64EncUtf8(att.name);
      console.log('[AttWidget.openPreview] Spreadsheet mode, att.url:', att.url, '→ pathB64:', pathB64);
      AttachmentsWidget._openCardOverlay('spreadsheet', { path: pathB64, title: titleB64 });
      return;
    }

    // 其他类型：系统默认程序打开
    const ea = window.electronAPI || window.parent?.electronAPI || window.top?.electronAPI;
    if (att.url.startsWith('file://') && ea?.openPath) {
      const filePath = att.url.replace(/^file:\/\/\/?/, '').replace(/\//g, '\\');
      ea.openPath(filePath);
    } else if (att.url.startsWith('http')) {
      window.open(att.url, '_blank');
    }
  }
}

// ─── 全局点击委托（grid cell 中的 data-att-preview 按钮）───────────────────────
;(function () {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-att-preview]');
    if (!btn) return;
    e.stopPropagation();
    try {
      const {attachment, parent_ref} = JSON.parse(_b64DecUtf8(btn.dataset.attPreview));
      AttachmentsWidget.openPreview(attachment, parent_ref).catch(error=>alert('附件读取失败：'+error.message));
    } catch (err) {
      console.error('[AttachmentsWidget] preview parse error', err);
    }
  });
})();

// ─── 内部辅助函数 ─────────────────────────────────────────────────────────────

/**
 * UTF-8 安全的 base64 编码（支持中文等非 ASCII 字符）
 * 用于 data-att-preview 属性和 openPreview 参数编码
 */
function _b64EncUtf8(str) {
  const bytes = new TextEncoder().encode(str);
  let binary = '';
  bytes.forEach(b => (binary += String.fromCharCode(b)));
  return btoa(binary);
}

/**
 * UTF-8 安全的 base64 解码（与 _b64EncUtf8 配对）
 */
function _b64DecUtf8(b64) {
  try {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  } catch (_) {
    return atob(b64); // fallback：兼容旧版 ASCII-only 数据
  }
}

function _attEsc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function _isAllowedMime(mime) {
  if (!mime) return false;
  return mime.startsWith('image/') ||
    mime.startsWith('text/') ||
    mime === 'application/pdf' ||
    mime === 'application/json' ||
    mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    mime === 'application/vnd.ms-excel';
}

/** 读取文件为 base64（不含 data: 前缀）*/


/** 图片压缩（canvas API，maxPx=1600，quality=0.7），返回 base64（不含前缀）*/
function _compressImage(file, maxPx, quality) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;
      if (width > maxPx || height > maxPx) {
        if (width > height) { height = Math.round(height * maxPx / width); width = maxPx; }
        else                { width  = Math.round(width  * maxPx / height); height = maxPx; }
      }
      const canvas = document.createElement('canvas');
      canvas.width  = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);
      const dataUrl = canvas.toDataURL('image/jpeg', quality);
      resolve(dataUrl.split(',')[1] || '');
    };
    img.onerror = reject;
    img.src = url;
  });
}

