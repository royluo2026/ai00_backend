'use strict';

// ── bridge 辅助 ──────────────────────────────────────────────────────────────
async function callBridge(ns, method, params = {}) {
  // 本地 bridge 已移除，md_workspace 功能暂不可用
  throw new Error('md_workspace bridge not available in cloud mode');
}

// ── 状态 ─────────────────────────────────────────────────────────────────────
let _docs = [];
let _currentFilename = null;
let _workspaceInfo   = null;
let _dirty = false;

// ── DOM 引用 ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── 初始化 ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  _bindToolbar();
  _bindTextarea();
  _loadDocs();
  _loadWorkspaceInfo();
});

// ── 加载文档列表 ─────────────────────────────────────────────────────────────
async function _loadDocs() {
  try {
    _docs = await callBridge('md', 'list_docs');
    _renderDocList();
  } catch (e) {
    console.error('[MdWorkspace] list_docs:', e);
  }
}

async function _loadWorkspaceInfo() {
  try {
    _workspaceInfo = await callBridge('md', 'get_workspace_info');
    $('workspace-info').textContent = `${_workspaceInfo.doc_count} 篇文档 · ${_fmtSize(_workspaceInfo.total_size)}`;
  } catch (_) {}
}

function _fmtSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function _fmtDate(mtime) {
  const d = new Date(mtime * 1000);
  return d.toLocaleDateString('zh-CN');
}

// ── 渲染文档列表 ─────────────────────────────────────────────────────────────
function _renderDocList() {
  const container = $('doc-list');
  container.innerHTML = '';
  if (!_docs.length) {
    container.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-faint,#6c7086);text-align:center">暂无文档</div>';
    return;
  }
  for (const doc of _docs) {
    const item = document.createElement('div');
    item.className = 'doc-item' + (doc.filename === _currentFilename ? ' active' : '');
    item.dataset.filename = doc.filename;
    item.innerHTML = `
      <div class="doc-item-title">${_escHtml(doc.title)}</div>
      <div class="doc-item-meta">${_escHtml(doc.filename)} · ${_fmtDate(doc.mtime)}</div>
    `;
    item.addEventListener('click', () => _openDoc(doc.filename));
    container.appendChild(item);
  }
}

// ── 打开文档 ─────────────────────────────────────────────────────────────────
async function _openDoc(filename) {
  if (_dirty && _currentFilename) {
    if (!confirm('当前文档有未保存的修改，确定切换？')) return;
    _dirty = false;
  }
  try {
    const { content } = await callBridge('md', 'read_doc', { filename });
    _currentFilename = filename;
    _dirty = false;
    $('md-textarea').value = content;
    $('current-filename').textContent = filename;
    $('save-status').textContent = '';
    $('empty-state').style.display  = 'none';
    $('editor-area').style.display  = '';
    // 默认进入编辑模式
    _setMode('edit');
    _renderDocList();
  } catch (e) {
    alert('打开文件失败: ' + e.message);
  }
}

// ── 保存文档 ─────────────────────────────────────────────────────────────────
async function _saveDoc() {
  if (!_currentFilename) return;
  const content = $('md-textarea').value;
  const btn = $('btn-save');
  btn.disabled = true;
  btn.textContent = '保存中…';
  try {
    await callBridge('md', 'write_doc', { filename: _currentFilename, content });
    _dirty = false;
    $('save-status').textContent = '已保存 ' + new Date().toLocaleTimeString('zh-CN');
    await _loadDocs();
    await _loadWorkspaceInfo();
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
  btn.disabled = false;
  btn.textContent = '保存';
}

// ── 新建文档 ─────────────────────────────────────────────────────────────────
function _newDoc() {
  const modal = document.getElementById('new-doc-modal');
  const input = document.getElementById('new-doc-title');
  if (!modal || !input) return;
  input.value = '新文档';
  modal.style.display = 'flex';
  setTimeout(() => { input.focus(); input.select(); }, 50);
}

async function _confirmNewDoc() {
  const modal = document.getElementById('new-doc-modal');
  const input = document.getElementById('new-doc-title');
  const title = input?.value?.trim();
  if (!title) return;
  modal.style.display = 'none';
  try {
    const { filename } = await callBridge('md', 'create_doc', { title });
    await _loadDocs();
    await _openDoc(filename);
  } catch (e) {
    alert('新建失败: ' + e.message);
  }
}

// ── 删除文档 ─────────────────────────────────────────────────────────────────
async function _deleteDoc() {
  if (!_currentFilename) return;
  if (!confirm(`确定删除 "${_currentFilename}"？此操作不可撤销。`)) return;
  try {
    await callBridge('md', 'delete_doc', { filename: _currentFilename });
    _currentFilename = null;
    _dirty = false;
    $('editor-area').style.display  = 'none';
    $('empty-state').style.display  = '';
    await _loadDocs();
    await _loadWorkspaceInfo();
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
}

// ── 模式切换（编辑 / 预览） ───────────────────────────────────────────────────
function _setMode(mode) {
  const isEdit = mode === 'edit';
  $('edit-pane').style.display    = isEdit ? '' : 'none';
  $('preview-pane').style.display = isEdit ? 'none' : '';
  $('btn-mode-edit').classList.toggle('active', isEdit);
  $('btn-mode-preview').classList.toggle('active', !isEdit);
  if (!isEdit) {
    const md = $('md-textarea').value;
    $('md-preview').innerHTML = typeof marked !== 'undefined'
      ? marked.parse(md) : _escHtml(md).replace(/\n/g, '<br>');
  }
}

// ── 导入 .md ─────────────────────────────────────────────────────────────────
async function _importMd() {
  const eApi = window.electronAPI;
  if (!eApi?.openMdDialog) { alert('仅 Electron 环境支持文件导入'); return; }
  const filePath = await eApi.openMdDialog();
  if (!filePath) return;
  try {
    const content = await eApi.readTextFile(filePath);
    if (_currentFilename) {
      $('md-textarea').value = content;
      _dirty = true;
      $('save-status').textContent = '已导入，请保存';
    } else {
      // 以原文件名新建
      const parts = filePath.replace(/\\/g, '/').split('/');
      const name  = parts[parts.length - 1];
      const title = name.replace(/\.md$/i, '');
      const { filename } = await callBridge('md', 'create_doc', { title });
      await callBridge('md', 'write_doc', { filename, content });
      await _loadDocs();
      await _openDoc(filename);
    }
  } catch (e) { alert('导入失败: ' + e.message); }
}

// ── 导出 .md ─────────────────────────────────────────────────────────────────
async function _exportMd() {
  if (!_currentFilename) return;
  const eApi = window.electronAPI;
  if (!eApi?.saveMdDialog) { alert('仅 Electron 环境支持文件导出'); return; }
  const savePath = await eApi.saveMdDialog(_currentFilename);
  if (!savePath) return;
  try {
    const content = $('md-textarea').value;
    await eApi.writeTextFile(savePath, content);
    alert('导出成功: ' + savePath);
  } catch (e) { alert('导出失败: ' + e.message); }
}

// ── 图片粘贴处理 ─────────────────────────────────────────────────────────────
async function _handleImagePaste(file) {
  const ts = Date.now();
  const ext = file.type.split('/')[1] || 'png';
  const filename = `img-${ts}.${ext}`;
  try {
    const b64 = await _fileToBase64(file);
    await callBridge('md', 'save_image', { filename, base64_data: b64 });
    _insertAtCursor(`![image](../assets/${filename})`);
  } catch (e) { console.warn('[MdWorkspace] 图片保存失败:', e); }
}

function _fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ── 光标插入文本 ─────────────────────────────────────────────────────────────
function _insertAtCursor(text) {
  const ta = $('md-textarea');
  const start = ta.selectionStart;
  const end   = ta.selectionEnd;
  ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
  ta.selectionStart = ta.selectionEnd = start + text.length;
  ta.focus();
  _dirty = true;
}

function _escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── 绑定工具栏按钮 ───────────────────────────────────────────────────────────
function _bindToolbar() {
  $('btn-new-doc')?.addEventListener('click',  _newDoc);
  $('btn-new-doc-2')?.addEventListener('click', _newDoc);
  $('btn-mode-edit')?.addEventListener('click',    () => _setMode('edit'));
  $('btn-mode-preview')?.addEventListener('click', () => _setMode('preview'));
  $('btn-import')?.addEventListener('click', _importMd);
  $('btn-export')?.addEventListener('click', _exportMd);
  $('btn-delete-doc')?.addEventListener('click', _deleteDoc);
  $('btn-save')?.addEventListener('click', _saveDoc);

  // 新建文档 modal 按钮
  document.getElementById('new-doc-cancel')?.addEventListener('click', () => {
    document.getElementById('new-doc-modal').style.display = 'none';
  });
  document.getElementById('new-doc-confirm')?.addEventListener('click', _confirmNewDoc);
  document.getElementById('new-doc-title')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') _confirmNewDoc();
    if (e.key === 'Escape') document.getElementById('new-doc-modal').style.display = 'none';
  });

  // MD 工具栏（B / I / code / … 按钮）
  document.querySelectorAll('.md-toolbar button[data-insert-before]').forEach(btn => {
    btn.addEventListener('click', () => {
      const before      = btn.dataset.insertBefore || '';
      const after       = btn.dataset.insertAfter  || '';
      const placeholder = btn.dataset.placeholder  || '';
      const ta = $('md-textarea');
      const sel = ta.value.slice(ta.selectionStart, ta.selectionEnd) || placeholder;
      const ins = before + sel + after;
      _insertAtCursor(ins);
    });
  });
}

// ── 绑定 textarea 事件 ───────────────────────────────────────────────────────
function _bindTextarea() {
  const ta = $('md-textarea');

  // 标记脏状态
  ta.addEventListener('input', () => {
    _dirty = true;
    $('save-status').textContent = '未保存';
  });

  // Ctrl+S 保存
  ta.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      _saveDoc();
    }
  });

  // 粘贴图片
  ta.addEventListener('paste', async e => {
    const items = [...(e.clipboardData?.items || [])];
    const imgItem = items.find(it => it.type.startsWith('image/'));
    if (imgItem) {
      e.preventDefault();
      await _handleImagePaste(imgItem.getAsFile());
    }
  });

  // 拖拽图片
  ta.addEventListener('drop', async e => {
    const files = [...(e.dataTransfer?.files || [])].filter(f => f.type.startsWith('image/'));
    if (files.length) {
      e.preventDefault();
      for (const f of files) await _handleImagePaste(f);
    }
  });
  ta.addEventListener('dragover', e => { if ([...(e.dataTransfer?.items || [])].some(it => it.type.startsWith('image/'))) e.preventDefault(); });
}

// ── 跨窗口消息：打开指定文件（knowledge.js 的"在 MD 中打开"按钮使用）─────────
window.addEventListener('message', e => {
  if (e.data?.type === 'open-doc' && e.data.filename) {
    _openDoc(e.data.filename);
  }
});
