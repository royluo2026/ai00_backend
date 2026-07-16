/**
 * cmd_palette.js — 命令面板（Ctrl+P）
 * 依赖：TabManager（window.TabManager）、dbg（window.dbg）、LogPanel（window.LogPanel）
 */
const CmdPalette = (() => {
  // 内置命令（不依赖后端）
  const _builtins = [
    { id: 'open.workbench', name: '打开工作台',       desc: '个人任务看板',    fn: () => window.TabManager.open('workbench') },
    { id: 'open.canvas',    name: '打开工艺画布',      desc: '工艺BOP编辑器',   fn: () => window.TabManager.open('canvas')    },
    { id: 'open.table',     name: '打开工艺表格',      desc: 'Excel风格表格',   fn: () => window.TabManager.open('table')     },
    { id: 'open.project',   name: '打开项目管理',      desc: '项目/车型管理',   fn: () => window.TabManager.open('project')   },
    { id: 'open.knowledge', name: '打开知识库',        desc: 'GBOP/工艺元素/知识清单', fn: () => window.TabManager.open('knowledge_hub') },
    { id: 'open.automation',name: '打开自动化与AI',    desc: '自动化画布/规则/Skill',  fn: () => window.TabManager.open('automation_hub') },
    { id: 'open.settings',  name: '打开设置',          desc: 'Ctrl+,',                 fn: () => window.TabManager.open('settings')  },
    { id: 'theme.toggle',   name: '切换深色/浅色主题', desc: '',                fn: () => window.ThemeManager.toggleTheme() },
    { id: 'debug.show',     name: '显示调试面板',      desc: 'Ctrl+`',         fn: () => window.dbg?.show()                  },
    { id: 'log.show',       name: '显示日志面板',      desc: '',               fn: () => window.LogPanel?.show()             },
  ];

  let _cmds = [..._builtins];
  let _filtered = [];
  let _selected = 0;

  /** 供插件/外部注册命令 */
  function register(cmd) {
    const idx = _cmds.findIndex(c => c.id === cmd.id);
    if (idx >= 0) _cmds[idx] = cmd; else _cmds.push(cmd);
  }

  function _render(query) {
    const q = (query || '').trim().toLowerCase();
    _filtered = q
      ? _cmds.filter(c =>
          c.name.toLowerCase().includes(q) ||
          c.id.toLowerCase().includes(q)   ||
          (c.desc || '').toLowerCase().includes(q))
      : _cmds;
    _selected = 0;

    const list = document.getElementById('cmd-results');
    list.innerHTML = '';
    _filtered.forEach((cmd, i) => {
      const el = document.createElement('div');
      el.className = 'cmd-item' + (i === 0 ? ' selected' : '');
      el.dataset.idx = i;
      el.innerHTML =
        `<span class="cmd-item-name">${_hl(cmd.name, q)}</span>` +
        (cmd.desc ? `<span class="cmd-item-desc">${cmd.desc}</span>` : '') +
        (cmd.key  ? `<span class="cmd-item-key">${cmd.key}</span>`   : '');
      el.addEventListener('mousedown', e => { e.preventDefault(); _execute(i); });
      el.addEventListener('mousemove', () => _highlight(i));
      list.appendChild(el);
    });
  }

  /** 高亮匹配字符 */
  function _hl(text, q) {
    if (!q) return text;
    const idx = text.toLowerCase().indexOf(q);
    if (idx < 0) return text;
    return text.slice(0, idx) +
           `<mark style="background:var(--color-primary);color:var(--text-on-primary);border-radius:2px;">${text.slice(idx, idx + q.length)}</mark>` +
           text.slice(idx + q.length);
  }

  function _highlight(idx) {
    _selected = idx;
    document.querySelectorAll('#cmd-results .cmd-item').forEach((el, i) =>
      el.classList.toggle('selected', i === idx));
  }

  function _execute(idx) {
    const cmd = _filtered[idx];
    if (!cmd) return;
    hide();
    try { cmd.fn(); }
    catch(e) { window.dbg?.error(`[Cmd] ${cmd.id} 执行异常: ${e}`); }
  }

  function show() {
    document.getElementById('cmd-overlay').classList.remove('hidden');
    const input = document.getElementById('cmd-input');
    input.value = '';
    _render('');
    requestAnimationFrame(() => input.focus());
  }

  function hide() {
    document.getElementById('cmd-overlay').classList.add('hidden');
  }

  function init() {
    const overlay = document.getElementById('cmd-overlay');
    const input   = document.getElementById('cmd-input');
    if (!overlay || !input) return;

    input.addEventListener('input', e => _render(e.target.value));
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); _highlight(Math.min(_selected + 1, _filtered.length - 1)); }
      if (e.key === 'ArrowUp')   { e.preventDefault(); _highlight(Math.max(_selected - 1, 0)); }
      if (e.key === 'Enter')     { e.preventDefault(); _execute(_selected); }
      if (e.key === 'Escape')    { e.preventDefault(); hide(); }
    });

    // 点击遮罩关闭
    overlay.addEventListener('mousedown', e => { if (e.target === overlay) hide(); });

    // 异步从后端拉取额外命令
    _loadBackendCmds();
  }

  async function _loadBackendCmds() {
    // 后端命令通过云端 API 加载（local Python bridge 已移除）
  }

  return { show, hide, register, init };
})();

window.CmdPalette = CmdPalette;

