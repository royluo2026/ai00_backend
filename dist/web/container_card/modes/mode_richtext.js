'use strict';
/**
 * mode_richtext.js — TipTap 富文本编辑器容器模式
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)
 *   renderFullPage(containerEl, urlParams)
 *
 * params:
 *   item_gid   : 知识条目 gid
 *   scope      : 'local' | 'cloud'（默认 local）
 *   readonly   : 'true' | 'false'（默认 false）
 *   title      : 初始标题（可选，用于新建时显示）
 *   content    : base64 编码的 TipTap JSON 字符串（内联内容，可选）
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['richtext'] = (() => {

  // ── TipTap 懒加载 ──────────────────────────────────────────────────────────
  let _tiptapLoaded = false;
  let _loadPromise  = null;

  function _loadTipTap() {
    if (_tiptapLoaded) return Promise.resolve();
    if (_loadPromise) return _loadPromise;
    _loadPromise = new Promise((resolve, reject) => {
      const base = (function _base() {
        try {
          const scripts = document.querySelectorAll('script[src]');
          for (const s of scripts) {
            const m = s.src.match(/(.*)container_card\//);
            if (m) return m[1];
          }
        } catch (_) {}
        return '../';
      })();
      const script = document.createElement('script');
      script.src = base + 'assets/lib/tiptap/tiptap-bundle.umd.js';
      script.onload = () => { _tiptapLoaded = true; resolve(); };
      script.onerror = () => reject(new Error('TipTap bundle 加载失败，请运行 tools/tiptap-bundler 打包'));
      document.head.appendChild(script);
    });
    return _loadPromise;
  }

  // ── 工具函数 ───────────────────────────────────────────────────────────────
  function _b64Dec(s) {
    try {
      const bin = atob(s);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    } catch (_) { return s; }
  }

  function _cf() {
    return window._cloudFetch || window.parent?._cloudFetch || null;
  }

  async function _loadContent(itemGid, scope) {
    if (!itemGid) return null;
    try {
      const _cloudFetch = _cf();
      if (!_cloudFetch) return null;
      const data = await _cloudFetch(`/api/knowledge_hub/items/${itemGid}`, { method: 'GET' });
      return data?.content_body || null;
    } catch (_) { return null; }
  }

  async function _saveContent(itemGid, scope, content) {
    if (!itemGid) return;
    try {
      const _cloudFetch = _cf();
      if (_cloudFetch) await _cloudFetch(`/api/knowledge_hub/items/${itemGid}`, {
        method: 'PATCH', body: JSON.stringify({ content_body: content }),
      });
    } catch (_) {}
  }

  // ── 工具栏 HTML ────────────────────────────────────────────────────────────
  function _toolbarHTML() {
    return `
<div class="rt-toolbar" role="toolbar">
  <button class="rt-btn" data-cmd="toggleBold" title="粗体 Ctrl+B"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 4h8a4 4 0 010 8H6V4z"/><path d="M6 12h9a4 4 0 010 8H6v-8z"/></svg></button>
  <button class="rt-btn" data-cmd="toggleItalic" title="斜体 Ctrl+I"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="4" x2="10" y2="4"/><line x1="14" y1="20" x2="5" y2="20"/><line x1="15" y1="4" x2="9" y2="20"/></svg></button>
  <button class="rt-btn" data-cmd="toggleStrike" title="删除线"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><path d="M16 6C16 6 14 4 12 4C9 4 7 6 7 8C7 10.6667 9 11.3333 12 12C15 12.6667 17 13.3333 17 16C17 18 15 20 12 20C9 20 7 18 7 18"/></svg></button>
  <span class="rt-sep"></span>
  <button class="rt-btn" data-cmd="toggleHeading1" title="标题 1">H1</button>
  <button class="rt-btn" data-cmd="toggleHeading2" title="标题 2">H2</button>
  <button class="rt-btn" data-cmd="toggleHeading3" title="标题 3">H3</button>
  <span class="rt-sep"></span>
  <button class="rt-btn" data-cmd="toggleBulletList" title="无序列表"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3" cy="6" r="1" fill="currentColor"/><circle cx="3" cy="12" r="1" fill="currentColor"/><circle cx="3" cy="18" r="1" fill="currentColor"/></svg></button>
  <button class="rt-btn" data-cmd="toggleOrderedList" title="有序列表"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/></svg></button>
  <button class="rt-btn" data-cmd="toggleBlockquote" title="引用"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3c0 1 0 1 1 1z"/></svg></button>
  <span class="rt-sep"></span>
  <button class="rt-btn" data-cmd="insertTable" title="插入表格"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="1"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="12" y1="3" x2="12" y2="21"/></svg></button>
  <button class="rt-btn" data-cmd="setHorizontalRule" title="分隔线"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg></button>
  <span class="rt-sep"></span>
  <!-- 文字颜色 -->
  <label class="rt-btn rt-color-label" title="文字颜色">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 7l3-5 3 5"/><path d="M5 17h14"/><path d="M12 2v15"/></svg>
    <input type="color" id="rtColorPicker" value="#f38ba8"
      style="position:absolute;opacity:0;width:0;height:0;pointer-events:none;" />
  </label>
  <button class="rt-btn" data-cmd="clearColor" title="清除颜色">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
  </button>
  <span class="rt-sep"></span>
  <!-- 插入图片 -->
  <button class="rt-btn" data-cmd="insertImage" title="插入图片">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
  </button>
  <span class="rt-sep"></span>
  <span class="rt-status" id="rtSaveStatus"></span>
</div>`;
  }

  const _CSS = `
<style id="rt-style">
.rt-wrap { display:flex; flex-direction:column; height:100%; overflow:hidden; }
.rt-toolbar {
  display:flex; align-items:center; gap:2px; padding:4px 8px;
  border-bottom:1px solid var(--border,#313244); flex-shrink:0;
  background:var(--bg2,#181825); flex-wrap:wrap;
}
.rt-btn {
  display:inline-flex; align-items:center; gap:3px;
  padding:3px 6px; border:none; border-radius:3px; cursor:pointer;
  font-size:12px; background:transparent; color:var(--text,#cdd6f4);
  transition:background .15s, color .15s;
}
.rt-btn:hover { background:var(--hover,#2a2a3d); }
.rt-btn.is-active { background:var(--active,#2d3561); color:var(--accent,#89b4fa); }
.rt-sep { width:1px; height:18px; background:var(--border,#313244); margin:0 4px; }
.rt-status { font-size:11px; color:var(--text-muted,#6c7086); margin-left:auto; }
.rt-color-label { cursor:pointer; position:relative; }
.rt-color-label:hover { background:var(--hover,#2a2a3d); }
.rt-body {
  flex:1; overflow-y:auto; padding:16px 24px; min-height:0;
}
.rt-body .ProseMirror {
  outline:none; min-height:200px;
  font-size:14px; line-height:1.7; color:var(--text,#cdd6f4);
}
.rt-body .ProseMirror p.is-editor-empty:first-child::before {
  content: attr(data-placeholder);
  color:var(--text-muted,#6c7086); pointer-events:none; float:left; height:0;
}
.rt-body .ProseMirror h1 { font-size:1.6em; font-weight:700; margin:1em 0 .4em; }
.rt-body .ProseMirror h2 { font-size:1.3em; font-weight:600; margin:1em 0 .4em; }
.rt-body .ProseMirror h3 { font-size:1.1em; font-weight:600; margin:1em 0 .4em; }
.rt-body .ProseMirror ul, .rt-body .ProseMirror ol { padding-left:1.6em; margin:.5em 0; }
.rt-body .ProseMirror blockquote {
  border-left:3px solid var(--accent,#89b4fa);
  padding-left:12px; margin:.5em 0; color:var(--text-muted,#6c7086);
}
.rt-body .ProseMirror hr { border:none; border-top:1px solid var(--border,#313244); margin:1em 0; }
.rt-body .ProseMirror table {
  border-collapse:collapse; margin:.5em 0; width:100%;
}
.rt-body .ProseMirror table td, .rt-body .ProseMirror table th {
  border:1px solid var(--border,#313244); padding:6px 10px; min-width:60px;
}
.rt-body .ProseMirror table th { background:var(--bg2,#181825); font-weight:600; }
.rt-body .ProseMirror img { max-width:100%; border-radius:4px; }
.rt-readonly .rt-toolbar { display:none; }
</style>`;

  // ── 主渲染 ─────────────────────────────────────────────────────────────────
  async function _render(el, params) {
    const itemGid  = params.item_gid || params.gid || '';
    const scope    = params.scope || 'local';
    const readonly = String(params.readonly) === 'true';

    // 注入样式（单例）
    if (!document.getElementById('rt-style')) {
      document.head.insertAdjacentHTML('beforeend', _CSS);
    }

    el.innerHTML = `<div class="rt-wrap${readonly ? ' rt-readonly' : ''}">
      ${readonly ? '' : _toolbarHTML()}
      <div class="rt-body" id="rtEditorBody"></div>
    </div>`;

    const editorEl = el.querySelector('#rtEditorBody');
    const statusEl = el.querySelector('#rtSaveStatus');

    // 加载 TipTap
    try {
      await _loadTipTap();
    } catch (e) {
      editorEl.innerHTML = `<div style="padding:16px;color:var(--text-muted,#888)">${e.message}</div>`;
      return;
    }

    const TT = window.TipTapBundle;
    if (!TT || !TT.Editor) {
      editorEl.innerHTML = `<div style="padding:16px;color:var(--text-muted,#888)">TipTap 加载失败</div>`;
      return;
    }

    // 加载内容
    let initialContent = null;
    if (params.content) {
      try { initialContent = JSON.parse(_b64Dec(params.content)); } catch (_) {}
    }
    if (!initialContent && itemGid) {
      initialContent = await _loadContent(itemGid, scope);
    }

    // 创建编辑器
    const extensions = [
      TT.StarterKit.configure({ history: true }),
      TT.Table.configure({ resizable: true }),
      TT.TableRow, TT.TableCell, TT.TableHeader,
      TT.Image.configure({ inline: false, allowBase64: true }),
      TT.TextStyle,
      TT.Color,
      TT.Placeholder?.configure({ placeholder: '开始输入内容…' }),
    ].filter(Boolean);

    const editor = new TT.Editor({
      element: editorEl,
      extensions,
      content: initialContent || '',
      editable: !readonly,
      onUpdate: readonly ? undefined : _debounce(async () => {
        if (statusEl) statusEl.textContent = '保存中…';
        await _saveContent(itemGid, scope, editor.getJSON());
        if (statusEl) statusEl.textContent = '已保存';
        setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 2000);
      }, 800),
      onSelectionUpdate: readonly ? undefined : () => _updateActive(editor, el),
    });

    // 工具栏按钮绑定
    if (!readonly) {
      const toolbar = el.querySelector('.rt-toolbar');
      if (toolbar) {
        toolbar.addEventListener('click', e => {
          const btn = e.target.closest('[data-cmd]');
          if (!btn) return;
          _execCmd(editor, btn.dataset.cmd, el);
        });

        // 颜色 picker
        const colorPicker = toolbar.querySelector('#rtColorPicker');
        const colorLabel  = toolbar.querySelector('.rt-color-label');
        if (colorLabel && colorPicker) {
          colorLabel.addEventListener('click', () => colorPicker.click());
          colorPicker.addEventListener('input', e => {
            editor.chain().focus().setColor(e.target.value).run();
          });
        }
      }
    }

    // cleanup
    el._rtEditor = editor;
    return () => { editor.destroy(); };
  }

  function _execCmd(editor, cmd, rootEl) {
    const chain = editor.chain().focus();
    switch (cmd) {
      case 'toggleBold':        chain.toggleBold().run(); break;
      case 'toggleItalic':      chain.toggleItalic().run(); break;
      case 'toggleStrike':      chain.toggleStrike().run(); break;
      case 'toggleHeading1':    chain.toggleHeading({ level: 1 }).run(); break;
      case 'toggleHeading2':    chain.toggleHeading({ level: 2 }).run(); break;
      case 'toggleHeading3':    chain.toggleHeading({ level: 3 }).run(); break;
      case 'toggleBulletList':  chain.toggleBulletList().run(); break;
      case 'toggleOrderedList': chain.toggleOrderedList().run(); break;
      case 'toggleBlockquote':  chain.toggleBlockquote().run(); break;
      case 'insertTable':
        chain.insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(); break;
      case 'setHorizontalRule': chain.setHorizontalRule().run(); break;
      case 'clearColor':        chain.unsetColor().run(); break;
      case 'insertImage':       _pickAndInsertImage(editor); break;
    }
    _updateActive(editor, rootEl || document);
  }

  async function _pickAndInsertImage(editor) {
    const eAPI = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;
    if (eAPI?.openFileDialog) {
      const filePath = await eAPI.openFileDialog(
        [{ name: '图片', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'] }]
      );
      if (!filePath) return;
      try {
        const base64 = await eAPI.readFileBase64?.(filePath);
        if (base64) {
          const ext = filePath.split('.').pop().toLowerCase();
          const mime = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
                         gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml' }[ext] || 'image/png';
          editor.chain().focus().setImage({ src: `data:${mime};base64,${base64}` }).run();
        }
      } catch (_) {}
    } else {
      // fallback：URL 输入
      const url = prompt('图片 URL：');
      if (url) editor.chain().focus().setImage({ src: url }).run();
    }
  }

  function _updateActive(editor, root) {
    const btns = (root.querySelector ? root : document).querySelectorAll('.rt-btn[data-cmd]');
    const activeMap = {
      toggleBold:        () => editor.isActive('bold'),
      toggleItalic:      () => editor.isActive('italic'),
      toggleStrike:      () => editor.isActive('strike'),
      toggleHeading1:    () => editor.isActive('heading', { level: 1 }),
      toggleHeading2:    () => editor.isActive('heading', { level: 2 }),
      toggleHeading3:    () => editor.isActive('heading', { level: 3 }),
      toggleBulletList:  () => editor.isActive('bulletList'),
      toggleOrderedList: () => editor.isActive('orderedList'),
      toggleBlockquote:  () => editor.isActive('blockquote'),
    };
    btns.forEach(btn => {
      const fn = activeMap[btn.dataset.cmd];
      if (fn) btn.classList.toggle('is-active', fn());
    });
  }

  function _debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  return {
    async renderInCard(el, params, _ctx) {
      return _render(el, params);
    },
    async renderFullPage(el, urlParams) {
      return _render(el, urlParams);
    },
  };
})();
