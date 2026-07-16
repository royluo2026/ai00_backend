'use strict';
/**
 * mode_script.js — 脚本文件读写（Monaco Editor）
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   path     : base64 编码的文件绝对路径
 *   lang     : 语言 hint（js/py/ts/yaml/json/sh），可从文件扩展名自动推断
 *   editable : 'true'（默认）| 'false'
 *
 * Monaco 懒加载策略：首次使用时动态注入 loader.js。
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['script'] = (() => {

  const MONACO_BASE = '../assets/lib/monaco/vs';

  const EXT_LANG = {
    js: 'javascript', mjs: 'javascript', cjs: 'javascript',
    ts: 'typescript',
    py: 'python',
    yaml: 'yaml', yml: 'yaml',
    json: 'json',
    sh: 'shell', bash: 'shell',
    css: 'css',
    html: 'html',
    md: 'markdown',
    sql: 'sql',
    xml: 'xml',
  };

  function _decodePath(b64) {
    if (!b64) return '';
    try { return atob(b64); } catch { return b64; }
  }

  function _filename(p) {
    if (!p) return '';
    return p.replace(/\\/g, '/').split('/').pop() || p;
  }

  function _extLang(p) {
    const ext = (p || '').split('.').pop().toLowerCase();
    return EXT_LANG[ext] || 'plaintext';
  }

  // Monaco 懒加载 ──────────────────────────────────────────────────────────
  let _monacoLoading = false;
  let _monacoCallbacks = [];

  function _loadMonaco(cb) {
    if (window.monaco) { cb(); return; }
    _monacoCallbacks.push(cb);
    if (_monacoLoading) return;
    _monacoLoading = true;

    const script = document.createElement('script');
    script.src = MONACO_BASE + '/loader.js';
    script.onerror = () => {
      console.warn('[mode_script] Monaco loader not found at', script.src);
      // fallback: notify all waiting callbacks anyway (they'll handle the null monaco)
      _monacoCallbacks.forEach(fn => fn());
      _monacoCallbacks = [];
    };
    script.onload = () => {
      window.require.config({ paths: { vs: MONACO_BASE } });
      window.require(['vs/editor/editor.main'], () => {
        _monacoLoading = false;
        _monacoCallbacks.forEach(fn => fn());
        _monacoCallbacks = [];
      });
    };
    document.head.appendChild(script);
  }

  // 主题同步 ───────────────────────────────────────────────────────────────
  function _monacoTheme() {
    return document.documentElement.dataset.theme === 'dark' ? 'vs-dark' : 'vs';
  }

  // ── 全屏渲染 ─────────────────────────────────────────────────────────────
  function renderFullPage(containerEl, urlParams) {
    let filePath = _decodePath(urlParams.path || '');
    const langHint = urlParams.lang || _extLang(filePath);
    const editable = urlParams.editable !== 'false';
    const api = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;

    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    // 工具栏
    const toolbar = document.createElement('div');
    toolbar.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--border-color,#e5e7eb);flex-shrink:0;';
    toolbar.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted,#999)" stroke-width="1.5">
        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
      </svg>
      <span id="scriptFilename" style="flex:1;font-size:12px;color:var(--text-primary,#333);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(_filename(filePath) || '（未选择文件）')}</span>
      <button id="scriptOpenBtn" style="padding:3px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;">打开文件</button>
      ${editable ? `<button id="scriptSaveBtn" style="padding:3px 10px;border:none;border-radius:4px;background:var(--accent,#3b82f6);color:#fff;cursor:pointer;font-size:12px;">保存</button>` : ''}
    `;
    containerEl.appendChild(toolbar);

    const editorContainer = document.createElement('div');
    editorContainer.style.cssText = 'flex:1;overflow:hidden;';
    containerEl.appendChild(editorContainer);

    let _editor = null;
    let _currentLang = langHint;

    async function _loadFile(path) {
      filePath = path;
      const fname = _filename(path);
      toolbar.querySelector('#scriptFilename').textContent = fname || '（未选择文件）';
      _currentLang = _extLang(path);

      if (!api?.readTextFile) {
        _editor?.setValue('// electronAPI.readTextFile 不可用');
        return;
      }
      try {
        const content = await api.readTextFile(path);
        if (_editor) {
          const model = window.monaco.editor.createModel(content || '', _currentLang);
          _editor.setModel(model);
        }
      } catch (err) {
        _editor?.setValue(`// 读取失败: ${err.message}`);
      }
    }

    _loadMonaco(() => {
      if (!window.monaco) {
        editorContainer.innerHTML = '<div style="padding:16px;color:var(--text-danger,#e53e3e);font-size:13px;">Monaco Editor 未安装。请将 Monaco 文件放置到 web/assets/lib/monaco/vs/ 目录。</div>';
        return;
      }

      _editor = window.monaco.editor.create(editorContainer, {
        value: '',
        language: _currentLang,
        theme: _monacoTheme(),
        readOnly: !editable,
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 13,
        scrollBeyondLastLine: false,
        wordWrap: 'on',
      });

      // Ctrl+S 保存
      if (editable) {
        _editor.addCommand(window.monaco.KeyMod.CtrlCmd | window.monaco.KeyCode.KeyS, async () => {
          await _doSave();
        });
      }

      // 主题切换监听
      window.addEventListener('message', e => {
        if (e.data?.type === 'theme' && window.monaco) {
          window.monaco.editor.setTheme(e.data.theme === 'dark' ? 'vs-dark' : 'vs');
        }
      });

      // 如果有初始文件路径则加载
      if (filePath) _loadFile(filePath);
    });

    async function _doSave() {
      if (!filePath || !_editor || !api?.writeTextFile) return;
      const saveBtn = toolbar.querySelector('#scriptSaveBtn');
      if (saveBtn) { saveBtn.textContent = '保存中…'; saveBtn.disabled = true; }
      try {
        await api.writeTextFile(filePath, _editor.getValue());
        if (saveBtn) { saveBtn.textContent = '已保存'; }
        setTimeout(() => { if (saveBtn) { saveBtn.textContent = '保存'; saveBtn.disabled = false; } }, 1500);
      } catch (err) {
        if (saveBtn) { saveBtn.textContent = '保存失败'; saveBtn.disabled = false; }
      }
    }

    toolbar.querySelector('#scriptOpenBtn')?.addEventListener('click', async () => {
      if (!api?.openFileDialog) return;
      const result = await api.openFileDialog([
        { name: '脚本文件', extensions: ['js','ts','py','yaml','yml','json','sh','bash','sql','md','txt','css','html','xml'] },
        { name: '所有文件', extensions: ['*'] },
      ]);
      if (result?.length) _loadFile(result[0]);
    });

    toolbar.querySelector('#scriptSaveBtn')?.addEventListener('click', _doSave);
  }

  // ── 卡片渲染（只读预览前20行） ───────────────────────────────────────────
  function renderInCard(containerEl, params, ctx) {
    const filePath = _decodePath(params.path || '');
    const editable = params.editable !== 'false';
    const api = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;

    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 10px;border-bottom:1px solid var(--border-color,#e5e7eb);flex-shrink:0;';
    header.innerHTML = `
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted,#999)" stroke-width="1.5">
        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
      </svg>
      <span style="flex:1;font-size:12px;color:var(--text-primary,#333);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(_filename(filePath) || '（未配置文件路径）')}</span>
      <button class="sc-expand-btn" style="padding:2px 8px;border:1px solid var(--border-color,#e5e7eb);border-radius:3px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:11px;">${editable ? '编辑' : '查看'}</button>
    `;
    containerEl.appendChild(header);

    const preview = document.createElement('pre');
    preview.style.cssText = 'flex:1;overflow:hidden;padding:8px 10px;margin:0;font-size:11px;color:var(--text-secondary,#555);font-family:monospace;background:var(--bg-code,#f8fafc);';
    preview.textContent = '加载中…';
    containerEl.appendChild(preview);

    if (filePath && api?.readTextFile) {
      api.readTextFile(filePath).then(content => {
        const lines = (content || '').split('\n').slice(0, 20);
        preview.textContent = lines.join('\n') + (content.split('\n').length > 20 ? '\n…' : '');
      }).catch(() => { preview.textContent = '（读取失败）'; });
    } else {
      preview.textContent = filePath ? '（electronAPI 不可用）' : '（未配置文件路径）';
    }

    header.querySelector('.sc-expand-btn')?.addEventListener('dblclick', () => {
      if (typeof window._ccPopOut === 'function') window._ccPopOut('script', params);
    });
    header.querySelector('.sc-expand-btn')?.addEventListener('click', () => {
      if (typeof window._ccPopOut === 'function') window._ccPopOut('script', params);
    });

    return null;
  }

  function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { renderInCard, renderFullPage };
})();
