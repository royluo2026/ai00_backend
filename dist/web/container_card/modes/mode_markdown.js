'use strict';
/**
 * mode_markdown.js — 本地 Markdown 读写
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   path      : base64 编码的绝对路径（有 path 则从文件加载）
 *   content   : base64 编码的 Markdown 内容（内联）
 *   editable  : 'true' | 'false'（默认 false）
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['markdown'] = (() => {

  // ── marked.js 封装 ────────────────────────────────────────────────────────
  function _renderMd(text) {
    if (window.marked) {
      try { return window.marked.parse(text); } catch (_) {}
    }
    // Fallback：纯文本
    return `<pre style="white-space:pre-wrap;word-break:break-word;font-family:inherit">${_esc(text)}</pre>`;
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function _b64DecUtf8(b64) {
    try {
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    } catch (_) {
      return atob(b64);
    }
  }

  // ── 文件 I/O（依赖 electronAPI）──────────────────────────────────────────
  function _eAPI() {
    return window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI || null;
  }

  /** 将 file:// URL 或普通路径转为原生系统路径（Node fs 可读） */
  function _toNativePath(p) {
    if (!p) return p;
    // 去掉 file:/// 前缀（Windows: file:///D:/... → D:/...）
    let native = p.replace(/^file:\/\/\//, '');
    // Windows: 把正斜杠转反斜杠
    if (native.match(/^[a-zA-Z]:/)) {
      native = native.replace(/\//g, '\\');
    }
    return native;
  }

  async function _readFile(path) {
    // http/https URL（云端文件）：直接 fetch
    if (/^https?:\/\//i.test(path)) {
      const res = await fetch(path);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.text();
    }
    // 本地路径：走 Electron IPC
    const api = _eAPI();
    if (!api?.readTextFile) throw new Error('electronAPI.readTextFile 不可用');
    return api.readTextFile(_toNativePath(path));
  }

  async function _writeFile(path, content) {
    // http/https URL（云端文件）：直接 fetch PUT，无需 _cloudFetch
    if (/^https?:\/\//i.test(path)) {
      const filename = path.split('/').pop();
      const baseUrl  = path.match(/^https?:\/\/[^/]+/)?.[0] || window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.('') || window._AI00_BASE || localStorage.getItem('ai00_backend_url') || '';
      const res = await fetch(`${baseUrl}/api/uploads/${filename}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return;
    }
    // 本地路径：走 Electron IPC
    const api = _eAPI();
    if (!api?.writeTextFile) throw new Error('electronAPI.writeTextFile 不可用');
    return api.writeTextFile(_toNativePath(path), content);
  }

  async function _openMdDialog() {
    const api = _eAPI();
    if (!api?.openMdDialog && !api?.openFileDialog) throw new Error('文件对话框不可用');
    if (api.openMdDialog) return api.openMdDialog();
    const result = await api.openFileDialog([{ name: 'Markdown', extensions: ['md', 'markdown', 'txt'] }]);
    return result?.[0] || null;
  }

  async function _saveMdDialog(defaultName) {
    const api = _eAPI();
    if (!api?.saveMdDialog && !api?.saveFileDialog) throw new Error('保存对话框不可用');
    if (api.saveMdDialog) return api.saveMdDialog(defaultName || 'document.md');
    return api.saveFileDialog({ defaultPath: defaultName || 'document.md', filters: [{ name: 'Markdown', extensions: ['md'] }] });
  }

  // ── 工具栏插入辅助 ────────────────────────────────────────────────────────
  function _insertAt(textarea, before, after) {
    const start = textarea.selectionStart;
    const end   = textarea.selectionEnd;
    const sel   = textarea.value.slice(start, end);
    const text  = before + sel + after;
    document.execCommand('insertText', false, text);
    textarea.setSelectionRange(start + before.length, start + before.length + sel.length);
    textarea.focus();
  }

  // ── 渲染 ─────────────────────────────────────────────────────────────────

  function _buildEditor(containerEl, initialContent, filePath, editable, onSaveDone) {
    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    let currentContent = initialContent || '';
    let currentPath    = filePath || null;
    let isEditMode     = false;

    // ── 顶部工具栏 ──
    const toolbar = document.createElement('div');
    toolbar.style.cssText = 'display:flex;align-items:center;gap:6px;padding:4px 10px;background:var(--cc-bg,#fff);border-bottom:1px solid var(--cc-border,#dcdcdc);flex-shrink:0;';

    if (editable) {
      const openBtn = document.createElement('button');
      openBtn.className = 'cc-btn';
      openBtn.textContent = '打开文件';
      openBtn.style.cssText = 'padding:3px 8px;border-radius:4px;border:1px solid var(--cc-border,#dcdcdc);background:var(--cc-bg2,#f7f6f3);color:var(--cc-text,#2e2e2e);font-size:12px;cursor:pointer;';
      openBtn.addEventListener('click', async () => {
        try {
          const path = await _openMdDialog();
          if (!path) return;
          currentPath = path;
          currentContent = await _readFile(path);
          if (isEditMode) {
            editorEl.value = currentContent;
          } else {
            previewEl.innerHTML = _renderMd(currentContent);
          }
          if (pathLabel) pathLabel.textContent = path.split(/[\\/]/).pop();
        } catch (e) { alert('打开失败: ' + e); }
      });
      toolbar.appendChild(openBtn);

      const saveBtn = document.createElement('button');
      saveBtn.className = 'cc-btn cc-btn-primary';
      saveBtn.textContent = '保存';
      saveBtn.style.cssText = 'padding:3px 8px;border-radius:4px;border:none;background:var(--cc-accent,#7b61ff);color:#fff;font-size:12px;cursor:pointer;';
      saveBtn.addEventListener('click', async () => {
        let path = currentPath;
        if (!path) {
          try { path = await _saveMdDialog(); }
          catch (e) { alert('保存失败: ' + e); return; }
          if (!path) return;
          currentPath = path;
        }
        const content = isEditMode ? editorEl.value : currentContent;
        try {
          await _writeFile(path, content);
          currentContent = content;
          if (pathLabel) pathLabel.textContent = path.split(/[\\/]/).pop();
          saveBtn.textContent = '已保存';
          setTimeout(() => { saveBtn.textContent = '保存'; }, 1500);
          onSaveDone?.();
        } catch (e) { alert('保存失败: ' + e); }
      });
      toolbar.appendChild(saveBtn);

      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'cc-btn';
      toggleBtn.textContent = '编辑';
      toggleBtn.style.cssText = 'padding:3px 8px;border-radius:4px;border:1px solid var(--cc-border,#dcdcdc);background:var(--cc-bg2,#f7f6f3);color:var(--cc-text,#2e2e2e);font-size:12px;cursor:pointer;';
      toggleBtn.addEventListener('click', () => {
        isEditMode = !isEditMode;
        toggleBtn.textContent = isEditMode ? '预览' : '编辑';
        mdToolbar.style.display = isEditMode ? '' : 'none';
        if (isEditMode) {
          editorEl.value = currentContent;
          editorEl.style.display = '';
          previewEl.style.display = 'none';
          editorEl.focus();
        } else {
          currentContent = editorEl.value;
          previewEl.innerHTML = _renderMd(currentContent);
          editorEl.style.display = 'none';
          previewEl.style.display = '';
        }
      });
      toolbar.appendChild(toggleBtn);
    }

    const pathLabel = document.createElement('span');
    pathLabel.style.cssText = 'margin-left:auto;font-size:11px;color:var(--cc-muted,#6e6e6e);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px;';
    pathLabel.textContent = filePath ? filePath.split(/[\\/]/).pop() : '';
    toolbar.appendChild(pathLabel);

    // ── 编辑工具栏（仅编辑模式显示）──
    const mdToolbar = document.createElement('div');
    mdToolbar.style.cssText = 'display:none;flex-shrink:0;';
    mdToolbar.className = 'cc-md-toolbar';

    const toolBtns = [
      { label: 'B',  title: '粗体',     wrap: ['**','**']   },
      { label: 'I',  title: '斜体',     wrap: ['_','_']     },
      { label: '`',  title: '行内代码', wrap: ['`','`']     },
      { label: '[]', title: '链接',     wrap: ['[','](url)']},
      { label: '—',  title: '水平线',   insert: '\n---\n'   },
      { label: '•',  title: '无序列表', prefix: '- '        },
    ];
    toolBtns.forEach(tb => {
      const btn = document.createElement('button');
      btn.className = 'cc-md-tool-btn';
      btn.textContent = tb.label;
      btn.title = tb.title;
      btn.addEventListener('click', () => {
        if (!editorEl) return;
        if (tb.wrap)   { _insertAt(editorEl, tb.wrap[0], tb.wrap[1]); }
        else if (tb.insert) { _insertAt(editorEl, tb.insert, ''); }
        else if (tb.prefix) {
          const start = editorEl.selectionStart;
          const lineStart = editorEl.value.lastIndexOf('\n', start - 1) + 1;
          editorEl.setSelectionRange(lineStart, lineStart);
          document.execCommand('insertText', false, tb.prefix);
        }
      });
      mdToolbar.appendChild(btn);
    });

    // ── 主内容区 ──
    const bodyWrap = document.createElement('div');
    bodyWrap.style.cssText = 'flex:1;overflow:hidden;position:relative;';

    const previewEl = document.createElement('div');
    previewEl.className = 'cc-md-preview';
    previewEl.style.cssText = 'padding:16px 20px;overflow-y:auto;height:100%;line-height:1.7;font-size:14px;color:var(--cc-text,#2e2e2e);';
    previewEl.innerHTML = _renderMd(currentContent);

    const editorEl = document.createElement('textarea');
    editorEl.className = 'cc-md-editor';
    editorEl.value = currentContent;
    editorEl.style.cssText = 'display:none;width:100%;height:100%;padding:16px 20px;background:var(--cc-bg,#fff);color:var(--cc-text,#2e2e2e);border:none;outline:none;font-family:"Fira Code","Cascadia Code",monospace;font-size:13px;line-height:1.7;resize:none;';

    // Ctrl+S 保存
    editorEl.addEventListener('keydown', e => {
      if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        toolbar.querySelector('.cc-btn-primary')?.click();
      }
    });

    bodyWrap.appendChild(previewEl);
    bodyWrap.appendChild(editorEl);

    containerEl.appendChild(toolbar);
    containerEl.appendChild(mdToolbar);
    containerEl.appendChild(bodyWrap);
  }

  // ── renderInCard ─────────────────────────────────────────────────────────

  function renderInCard(containerEl, params, ctx) {
    const editable = params?.editable === true || params?.editable === 'true';
    const pathB64  = params?.path;
    const contentB64 = params?.content;

    containerEl.innerHTML = '<div style="padding:8px;font-size:12px;color:var(--cc-muted,#6e6e6e)">加载中…</div>';
    let destroyed = false;

    async function load() {
      let text = '';
      try {
        if (pathB64) {
          const path = _b64DecUtf8(pathB64);
          text = await _readFile(path);
        } else if (contentB64) {
          text = atob(contentB64);
        }
      } catch (e) {
        text = `*加载失败: ${e}*`;
      }
      if (destroyed) return;

      // 卡片模式：只读预览，双击弹出全屏
      containerEl.innerHTML = '';
      containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;cursor:pointer;';

      const preview = document.createElement('div');
      preview.className = 'cc-md-preview';
      preview.style.cssText = 'flex:1;overflow:hidden;padding:10px 12px;font-size:12px;line-height:1.6;color:var(--cc-text,#2e2e2e);';
      preview.innerHTML = _renderMd(text);

      const hint = document.createElement('div');
      hint.style.cssText = 'text-align:center;font-size:11px;color:var(--cc-accent,#7b61ff);padding:4px;border-top:1px solid var(--cc-border,#dcdcdc);cursor:pointer;flex-shrink:0;';
      hint.textContent = '双击编辑 →';

      function popOut() {
        const parent = window.parent;
        if (!parent?.TabManager) return;
        parent.TabManager.open('container_card', {
          mode: 'markdown',
          path: pathB64,
          content: contentB64 || btoa(unescape(encodeURIComponent(text))),
          editable: 'true',
          title: pathB64 ? atob(pathB64).split(/[\\/]/).pop() : 'Markdown 文件',
        });
      }

      containerEl.addEventListener('dblclick', popOut);
      hint.addEventListener('click', popOut);

      containerEl.appendChild(preview);
      if (editable) containerEl.appendChild(hint);
    }

    load();
    return () => { destroyed = true; };
  }

  // ── renderFullPage ───────────────────────────────────────────────────────

  async function renderFullPage(containerEl, urlParams) {
    const pathB64    = urlParams.get('path');
    const contentB64 = urlParams.get('content');
    const editable   = urlParams.get('editable') !== 'false';

    let initialText = '';
    let filePath    = null;

    containerEl.innerHTML = '<div class="cc-loading">加载中…</div>';

    try {
      if (pathB64) {
        filePath = _b64DecUtf8(pathB64);
        initialText = await _readFile(filePath);
      } else if (contentB64) {
        initialText = decodeURIComponent(escape(atob(contentB64)));
      }
    } catch (e) {
      initialText = `> *加载失败: ${e}*`;
    }

    _buildEditor(containerEl, initialText, filePath, editable, null);

    // 更新标题：优先使用传入的 title 参数，否则用文件路径
    const titleEl = document.getElementById('ccTitle');
    if (titleEl) {
      const titleParam = urlParams.get('title') || '';
      if (titleParam) {
        try { titleEl.textContent = _b64DecUtf8(titleParam); } catch (_) { titleEl.textContent = titleParam; }
      } else if (filePath) {
        titleEl.textContent = filePath.split(/[\\/]/).pop();
      }
    }
  }

  return { renderInCard, renderFullPage };
})();
