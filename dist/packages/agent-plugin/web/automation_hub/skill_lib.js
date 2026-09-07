/**
 * web/automation_hub/skill_lib.js
 * Skill 库管理页面逻辑
 */
(function () {
  'use strict';

  // ── 状态 ──────────────────────────────────────────────────────────────────
  let _skills = [];
  let _selected = null;       // 当前选中行
  let _editSkill = null;      // 编辑弹窗当前 skill（null=新建）
  let _newStep = 0;           // 分步 modal：0=关闭，1=选类型，2=填信息
  let _newType = '';          // 分步 modal 选中类型

  // 过滤条件
  let _filterScope  = 'all';   // all | mine | team | global
  let _filterType   = 'all';   // all | prompt | tool | flow
  let _filterStatus = 'all';   // all | active | draft | archived
  let _searchQ = '';

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const $gridBody   = document.getElementById('slGridBody');
  const $searchInp  = document.getElementById('slSearch');
  const $newBtn     = document.getElementById('slNewBtn');

  // ── 工具函数 ──────────────────────────────────────────────────────────────
  function _esc(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function _getUserGid() {
    try { return window.parent?._authUser?.gid || window.top?._authUser?.gid || ''; }
    catch (_) { return ''; }
  }

  function _typeName(t) {
    return { prompt: '提示词', tool: '工具', flow: '流程' }[t] || t;
  }
  function _scopeName(s) {
    return { private: '私有', team: '团队', global: '全局' }[s] || s;
  }
  function _statusName(s) {
    return { draft: '草稿', active: '激活', archived: '归档' }[s] || s;
  }

  // ── 云端 API ───────────────────────────────────────────────────────────────
  function _cf() { return window.parent?._cloudFetch || window._cloudFetch; }

  async function _invokeCapability(id, payload = {}) {
    const _cloudFetch = _cf();
    if (!_cloudFetch) throw new Error('云端服务未连接');
    const response = await _cloudFetch(`/api/v1/capabilities/${id}:invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version: 1, payload }),
    });
    const envelope = response?.data;
    if (response?.success !== true || envelope?.ok !== true) {
      const detail = envelope?.error || response?.error || {};
      throw new Error(detail.message || `能力调用失败：${id}@1`);
    }
    const value = envelope.data;
    return value?.data !== undefined && Object.keys(value).length === 1 ? value.data : value;
  }

  // ── 加载数据 ──────────────────────────────────────────────────────────────
  async function loadSkills() {
    try {
      const _cloudFetch = _cf();
      if (!_cloudFetch) { _skills = []; renderGrid(); return; }
      const list = await _cloudFetch(`/api/skills?scope_filter=all`, { method: 'GET' });
      _skills = Array.isArray(list) ? list : [];
    } catch (e) {
      _skills = [];
      console.warn('[skill_lib] list_skills 失败', e);
    }
    renderGrid();
  }

  // ── 渲染表格 ──────────────────────────────────────────────────────────────
  function renderGrid() {
    let rows = _skills.filter(s => {
      if (_filterScope !== 'all') {
        if (_filterScope === 'mine' && s.owner_gid !== _getUserGid() && !s.is_system) return false;
        if (_filterScope === 'team' && s.scope !== 'team') return false;
        if (_filterScope === 'global' && s.scope !== 'global') return false;
      }
      if (_filterType !== 'all' && s.skill_type !== _filterType) return false;
      if (_filterStatus !== 'all' && s.status !== _filterStatus) return false;
      if (_searchQ) {
        const q = _searchQ.toLowerCase();
        if (!s.name.toLowerCase().includes(q) && !s.title.includes(_searchQ) &&
            !(s.description || '').includes(_searchQ)) return false;
      }
      return true;
    });

    if (!$gridBody) return;
    if (!rows.length) {
      $gridBody.innerHTML = `<tr><td colspan="7" class="sl-empty">暂无 Skill</td></tr>`;
      return;
    }
    $gridBody.innerHTML = rows.map(s => {
      const isSystem = s.is_system;
      const sysTag = isSystem ? `<span class="sl-badge system">系统</span> ` : '';
      return `<tr data-gid="${s.gid}" class="${_selected?.gid === s.gid ? 'selected' : ''}">
        <td class="name-col">${_esc(s.icon || '')} ${_esc(s.name)}</td>
        <td>${_esc(s.title)}</td>
        <td><span class="sl-badge ${s.skill_type}">${_typeName(s.skill_type)}</span></td>
        <td><span class="sl-badge ${s.status}">${_statusName(s.status)}</span></td>
        <td><span class="sl-badge ${s.scope}">${_scopeName(s.scope)}</span></td>
        <td>${sysTag}${_esc((s.description || '').slice(0, 40))}</td>
        <td style="white-space:nowrap; text-align:right">
          ${!isSystem ? `<button class="sl-btn ghost" style="font-size:10px;padding:3px 8px" data-action="toggle-status" data-gid="${s.gid}">
            ${s.status === 'active' ? '归档' : '激活'}
          </button>` : ''}
        </td>
      </tr>`;
    }).join('');

    $gridBody.querySelectorAll('tr[data-gid]').forEach(tr => {
      tr.addEventListener('click', e => {
        if (e.target.closest('[data-action]')) return;
        const gid = tr.dataset.gid;
        const skill = _skills.find(s => s.gid === gid);
        if (skill) openEditModal(skill);
      });
      tr.querySelector('[data-action="toggle-status"]')?.addEventListener('click', e => {
        e.stopPropagation();
        const gid = e.currentTarget.dataset.gid;
        const skill = _skills.find(s => s.gid === gid);
        if (!skill) return;
        const newStatus = skill.status === 'active' ? 'archived' : 'active';
        const _cloudFetch = _cf();
        if (_cloudFetch) {
          _cloudFetch(`/api/skills/${gid}`, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ status: newStatus }) }).then(() => loadSkills());
        }
      });
    });
  }

  // ── 过滤器绑定 ─────────────────────────────────────────────────────────────
  function bindFilters() {
    document.querySelectorAll('[data-filter-scope]').forEach(el => {
      el.addEventListener('click', () => {
        _filterScope = el.dataset.filterScope;
        document.querySelectorAll('[data-filter-scope]').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        renderGrid();
      });
    });
    document.querySelectorAll('[data-filter-type]').forEach(el => {
      el.addEventListener('click', () => {
        _filterType = el.dataset.filterType;
        document.querySelectorAll('[data-filter-type]').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        renderGrid();
      });
    });
    document.querySelectorAll('[data-filter-status]').forEach(el => {
      el.addEventListener('click', () => {
        _filterStatus = el.dataset.filterStatus;
        document.querySelectorAll('[data-filter-status]').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        renderGrid();
      });
    });
    if ($searchInp) {
      $searchInp.addEventListener('input', () => {
        _searchQ = $searchInp.value.trim();
        renderGrid();
      });
    }
  }

  // ── 新建分步 Modal ─────────────────────────────────────────────────────────
  function openNewModal() {
    _newStep = 1;
    _newType = '';
    document.querySelectorAll('.sl-type-card').forEach(c => c.classList.remove('selected'));
    document.getElementById('slNewModal').classList.remove('hidden');
    document.getElementById('slNewStep1').style.display = '';
    document.getElementById('slNewStep2').style.display = 'none';
    document.getElementById('slNewNextBtn').disabled = true;
    document.getElementById('slNewTitle').textContent = '新建 Skill — 选择类型';
  }

  function closeNewModal() {
    document.getElementById('slNewModal').classList.add('hidden');
    _newStep = 0; _newType = '';
  }

  function bindNewModal() {
    document.querySelectorAll('.sl-type-card').forEach(card => {
      card.addEventListener('click', () => {
        document.querySelectorAll('.sl-type-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        _newType = card.dataset.type;
        document.getElementById('slNewNextBtn').disabled = false;
      });
    });

    document.getElementById('slNewNextBtn').addEventListener('click', () => {
      if (!_newType) return;
      _newStep = 2;
      document.getElementById('slNewTitle').textContent = `新建 Skill — ${{'prompt':'提示词模板','tool':'自定义工具','flow':'工作流关联'}[_newType]}`;
      document.getElementById('slNewStep1').style.display = 'none';
      _renderNewStep2(_newType);
      document.getElementById('slNewStep2').style.display = '';
    });

    document.getElementById('slNewBackBtn').addEventListener('click', () => {
      _newStep = 1;
      document.getElementById('slNewTitle').textContent = '新建 Skill — 选择类型';
      document.getElementById('slNewStep1').style.display = '';
      document.getElementById('slNewStep2').style.display = 'none';
    });

    document.getElementById('slNewSaveBtn').addEventListener('click', saveNewSkill);
    document.getElementById('slNewCancelBtn').addEventListener('click', closeNewModal);
    document.getElementById('slNewCloseBtn').addEventListener('click', closeNewModal);
    document.getElementById('slNewModal').addEventListener('click', e => {
      if (e.target === document.getElementById('slNewModal')) closeNewModal();
    });
  }

  function _renderNewStep2(type) {
    const $c = document.getElementById('slNewStep2');
    let typeFields = '';

    if (type === 'prompt') {
      typeFields = `
        <div class="sl-field">
          <label class="sl-label">提示词模板 <span class="required">*</span></label>
          <textarea class="sl-textarea" id="slNTemplate" rows="5" placeholder="使用 {{变量名}} 作为变量占位符…"></textarea>
          <span class="sl-hint">示例：请分析 {{topic}} 的工艺规范…</span>
        </div>
        <div class="sl-field">
          <label class="sl-label">变量列表</label>
          <div class="sl-var-editor" id="slNVarEditor"></div>
          <button class="sl-btn-add-var" id="slNAddVar" type="button">+ 添加变量</button>
        </div>`;
    } else if (type === 'tool') {
      typeFields = `
        <div class="sl-field">
          <label class="sl-label">Input Schema (JSON)</label>
          <textarea class="sl-textarea code" id="slNInputSchema" rows="4" placeholder='{"type":"object","properties":{"keyword":{"type":"string","description":"关键词"}}}'></textarea>
        </div>
        <div class="sl-field">
          <label class="sl-label">工具脚本 (Python) <span class="required">*</span></label>
          <textarea class="sl-textarea code" id="slNScript" rows="8" placeholder="def run(inputs):\n    keyword = inputs.get('keyword', '')\n    return {'result': keyword}"></textarea>
          <span class="sl-hint">必须定义 run(inputs) 函数，inputs 为 dict，return 任意可序列化对象</span>
        </div>
        <div class="sl-field" style="flex-direction:row;align-items:center;gap:8px">
          <input type="checkbox" id="slNNeedConfirm">
          <label for="slNNeedConfirm" class="sl-hint" style="cursor:pointer">执行前需要用户确认</label>
        </div>`;
    } else if (type === 'flow') {
      typeFields = `
        <div class="sl-field">
          <label class="sl-label">关联流程</label>
          <select class="sl-select" id="slNFlowGid">
            <option value="">加载中…</option>
          </select>
        </div>`;
      // flow 类型：加载流程列表
      setTimeout(async () => {
        try {
          const data = await _invokeCapability('agent.flow.read', { operation: 'list' });
          const flows = data?.flows || (Array.isArray(data) ? data : []);
          const sel = document.getElementById('slNFlowGid');
          if (!sel) return;
          sel.innerHTML = '<option value="">— 选择流程 —</option>' +
            flows.map(f => `<option value="${_esc(f.gid)}">${_esc(f.name)}</option>`).join('');
        } catch (_) {}
      }, 0);
    }

    $c.innerHTML = `<div class="sl-form">
      <div class="sl-form-row">
        <div class="sl-field">
          <label class="sl-label">标识符 (name) <span class="required">*</span></label>
          <input class="sl-input" id="slNName" placeholder="my_skill（小写字母+数字+下划线）">
          <span class="sl-hint">@触发时使用，全局唯一，创建后不可修改</span>
        </div>
        <div class="sl-field">
          <label class="sl-label">显示名 <span class="required">*</span></label>
          <input class="sl-input" id="slNTitle" placeholder="我的 Skill">
        </div>
      </div>
      <div class="sl-form-row">
        <div class="sl-field">
          <label class="sl-label">说明</label>
          <input class="sl-input" id="slNDesc" placeholder="Skill 的功能描述">
        </div>
        <div class="sl-field" style="max-width:100px">
          <label class="sl-label">可见范围</label>
          <select class="sl-select" id="slNScope">
            <option value="private">私有</option>
            <option value="team">团队</option>
            <option value="global">全局</option>
          </select>
        </div>
      </div>
      ${typeFields}
    </div>`;

    // 绑定变量列表按钮
    if (type === 'prompt') {
      document.getElementById('slNAddVar')?.addEventListener('click', () => _addVarRow('slNVarEditor'));
    }
  }

  function _addVarRow(editorId, varData = {}) {
    const $ed = document.getElementById(editorId);
    if (!$ed) return;
    const idx = $ed.children.length;
    const div = document.createElement('div');
    div.className = 'sl-var-row';
    div.dataset.idx = idx;
    div.innerHTML = `
      <input class="name" type="text" placeholder="变量名" value="${_esc(varData.name || '')}">
      <input class="label" type="text" placeholder="标签文字" value="${_esc(varData.label || '')}">
      <input class="default" type="text" placeholder="默认值" value="${_esc(varData.default || '')}">
      <label class="sl-var-req"><input type="checkbox" ${varData.required ? 'checked' : ''}> 必填</label>
      <button class="sl-var-del" type="button" title="删除">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>`;
    div.querySelector('.sl-var-del').addEventListener('click', () => div.remove());
    $ed.appendChild(div);
  }

  function _collectVars(editorId) {
    const $ed = document.getElementById(editorId);
    if (!$ed) return [];
    return Array.from($ed.querySelectorAll('.sl-var-row')).map(row => ({
      name:     row.querySelector('.name')?.value || '',
      label:    row.querySelector('.label')?.value || '',
      required: row.querySelector('input[type=checkbox]')?.checked || false,
      default:  row.querySelector('.default')?.value || '',
    })).filter(v => v.name);
  }

  async function saveNewSkill() {
    const name  = document.getElementById('slNName')?.value.trim();
    const title = document.getElementById('slNTitle')?.value.trim();
    const desc  = document.getElementById('slNDesc')?.value.trim() || '';
    const scope = document.getElementById('slNScope')?.value || 'private';
    if (!name || !title) { alert('标识符和显示名不能为空'); return; }

    let content = {};
    if (_newType === 'prompt') {
      content = {
        template:  document.getElementById('slNTemplate')?.value || '',
        variables: _collectVars('slNVarEditor'),
        system_hint: '',
      };
    } else if (_newType === 'tool') {
      let inputSchema = {};
      try { inputSchema = JSON.parse(document.getElementById('slNInputSchema')?.value || '{}'); } catch (_) {}
      content = {
        script:       document.getElementById('slNScript')?.value || '',
        input_schema: inputSchema,
        description:  desc,
        need_confirm: document.getElementById('slNNeedConfirm')?.checked || false,
      };
    } else if (_newType === 'flow') {
      content = { flow_gid: document.getElementById('slNFlowGid')?.value || '' };
    }

    try {
      const _cloudFetch = _cf();
      if (!_cloudFetch) { alert('需要飞书登录才能保存'); return; }
      const result = await _cloudFetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name, title, skill_type: _newType, scope, description: desc,
          owner_gid: _getUserGid(),
          content: JSON.stringify(content),
        }),
      });
      if (result?.error) { alert(result.error); return; }
      closeNewModal();
      await loadSkills();
    } catch (e) {
      alert('保存失败: ' + e.message);
    }
  }

  // ── 编辑 Modal ─────────────────────────────────────────────────────────────
  function openEditModal(skill) {
    _editSkill = skill;
    const isSystem = skill.is_system;
    let content = {};
    try { content = JSON.parse(skill.content || '{}'); } catch (_) {}

    const $overlay = document.getElementById('slEditOverlay');
    const $title   = document.getElementById('slEditTitle');
    const $body    = document.getElementById('slEditBody');
    if (!$overlay) return;

    $title.textContent = `${skill.title} (@${skill.name})`;
    $body.innerHTML = _renderEditForm(skill, content, isSystem);

    // 恢复变量行
    if (skill.skill_type === 'prompt' && !isSystem) {
      const vars = content.variables || [];
      vars.forEach(v => _addVarRow('slEditVarEditor', v));
      document.getElementById('slEditAddVar')?.addEventListener('click', () => _addVarRow('slEditVarEditor'));
    }

    // 底部按钮
    document.getElementById('slEditSaveBtn').style.display = isSystem ? 'none' : '';
    document.getElementById('slEditDeleteBtn').style.display = isSystem ? 'none' : '';
    document.getElementById('slEditToggleBtn').textContent = skill.status === 'active' ? '归档' : '激活';
    document.getElementById('slEditToggleBtn').style.display = isSystem ? 'none' : '';

    $overlay.classList.remove('hidden');
  }

  function _renderEditForm(skill, content, isSystem) {
    const ro = isSystem ? 'readonly disabled' : '';
    let typeFields = '';

    if (skill.skill_type === 'prompt') {
      const vars = content.variables || [];
      typeFields = `
        <div class="sl-field">
          <label class="sl-label">提示词模板</label>
          <textarea class="sl-textarea" id="slEditTemplate" rows="6" ${ro}>${_esc(content.template || '')}</textarea>
        </div>
        <div class="sl-field">
          <label class="sl-label">变量列表</label>
          <div class="sl-var-editor" id="slEditVarEditor"></div>
          ${!isSystem ? `<button class="sl-btn-add-var" id="slEditAddVar" type="button">+ 添加变量</button>` : ''}
        </div>`;
    } else if (skill.skill_type === 'tool') {
      typeFields = `
        <div class="sl-field">
          <label class="sl-label">Input Schema (JSON)</label>
          <textarea class="sl-textarea code" id="slEditInputSchema" rows="4" ${ro}>${_esc(JSON.stringify(content.input_schema || {}, null, 2))}</textarea>
        </div>
        <div class="sl-field">
          <label class="sl-label">工具脚本 (Python)</label>
          <textarea class="sl-textarea code" id="slEditScript" rows="8" ${ro}>${_esc(content.script || '')}</textarea>
        </div>
        <div class="sl-field" style="flex-direction:row;align-items:center;gap:8px">
          <input type="checkbox" id="slEditNeedConfirm" ${content.need_confirm ? 'checked' : ''} ${ro}>
          <label for="slEditNeedConfirm" class="sl-hint" style="cursor:pointer">执行前需要用户确认</label>
        </div>`;
    } else if (skill.skill_type === 'flow') {
      typeFields = `<div class="sl-field">
        <label class="sl-label">关联流程 GID</label>
        <input class="sl-input" id="slEditFlowGid" value="${_esc(content.flow_gid || '')}" ${ro}>
      </div>`;
    }

    return `<div class="sl-form">
      <div class="sl-form-row">
        <div class="sl-field">
          <label class="sl-label">标识符 (name)</label>
          <input class="sl-input" value="${_esc(skill.name)}" readonly disabled>
        </div>
        <div class="sl-field">
          <label class="sl-label">显示名</label>
          <input class="sl-input" id="slEditTitle2" value="${_esc(skill.title)}" ${ro}>
        </div>
      </div>
      <div class="sl-form-row">
        <div class="sl-field">
          <label class="sl-label">说明</label>
          <input class="sl-input" id="slEditDesc" value="${_esc(skill.description || '')}" ${ro}>
        </div>
        <div class="sl-field" style="max-width:100px">
          <label class="sl-label">可见范围</label>
          <select class="sl-select" id="slEditScope" ${ro}>
            ${['private','team','global'].map(s =>
              `<option value="${s}" ${skill.scope===s?'selected':''}>${_scopeName(s)}</option>`
            ).join('')}
          </select>
        </div>
      </div>
      ${typeFields}
      ${isSystem ? '<p class="sl-hint" style="color:var(--yellow)">系统预设 Skill，所有字段只读</p>' : ''}
    </div>`;
  }

  function closeEditModal() {
    document.getElementById('slEditOverlay')?.classList.add('hidden');
    _editSkill = null;
  }

  async function saveEditSkill() {
    if (!_editSkill) return;
    const s = _editSkill;
    const fields = {
      title:       document.getElementById('slEditTitle2')?.value || s.title,
      description: document.getElementById('slEditDesc')?.value || '',
      scope:       document.getElementById('slEditScope')?.value || s.scope,
    };

    let content = {};
    try { content = JSON.parse(s.content || '{}'); } catch (_) {}
    if (s.skill_type === 'prompt') {
      content.template  = document.getElementById('slEditTemplate')?.value || '';
      content.variables = _collectVars('slEditVarEditor');
    } else if (s.skill_type === 'tool') {
      try { content.input_schema = JSON.parse(document.getElementById('slEditInputSchema')?.value || '{}'); } catch (_) {}
      content.script       = document.getElementById('slEditScript')?.value || '';
      content.need_confirm = document.getElementById('slEditNeedConfirm')?.checked || false;
    } else if (s.skill_type === 'flow') {
      content.flow_gid = document.getElementById('slEditFlowGid')?.value || '';
    }
    fields.content = JSON.stringify(content);

    try {
      const _cloudFetch = _cf();
      if (!_cloudFetch) { alert('需要飞书登录才能保存'); return; }
      const result = await _cloudFetch(`/api/skills/${s.gid}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      });
      if (result?.error) { alert(result.error); return; }
      closeEditModal();
      await loadSkills();
    } catch (e) { alert('保存失败: ' + e.message); }
  }

  async function deleteEditSkill() {
    if (!_editSkill) return;
    if (!confirm(`确认删除 Skill「${_editSkill.title}」？此操作不可恢复。`)) return;
    try {
      const _cloudFetch = _cf();
      if (_cloudFetch) await _cloudFetch(`/api/skills/${_editSkill.gid}`, { method: 'DELETE' });
      closeEditModal();
      await loadSkills();
    } catch (e) { alert('删除失败: ' + e.message); }
  }

  async function toggleEditSkillStatus() {
    if (!_editSkill) return;
    const newStatus = _editSkill.status === 'active' ? 'archived' : 'active';
    try {
      const _cloudFetch = _cf();
      if (_cloudFetch) await _cloudFetch(`/api/skills/${_editSkill.gid}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      closeEditModal();
      await loadSkills();
    } catch (e) { alert('操作失败: ' + e.message); }
  }

  // ── 测试执行 Modal ─────────────────────────────────────────────────────────
  function openTestModal() {
    if (!_editSkill) return;
    const s = _editSkill;
    let content = {};
    try { content = JSON.parse(s.content || '{}'); } catch (_) {}

    const $overlay = document.getElementById('slTestOverlay');
    const $body    = document.getElementById('slTestBody');
    if (!$overlay) return;

    document.getElementById('slTestTitle').textContent = `测试执行 — ${s.title}`;
    document.getElementById('slTestResult').textContent = '（点击"执行"按钮查看结果）';

    let varFields = '';
    if (s.skill_type === 'prompt') {
      const vars = content.variables || [];
      varFields = vars.map(v => `
        <div class="sl-field">
          <label class="sl-label">${_esc(v.label || v.name)}</label>
          <input class="sl-input" style="font-size:12px" data-var="${_esc(v.name)}" value="${_esc(v.default || '')}">
        </div>`).join('');
    } else if (s.skill_type === 'tool') {
      const props = content.input_schema?.properties || {};
      varFields = Object.entries(props).map(([k, v]) => `
        <div class="sl-field">
          <label class="sl-label">${_esc(k)}<span class="sl-hint" style="margin-left:4px">${_esc(v.description||'')}</span></label>
          <input class="sl-input" style="font-size:12px" data-var="${_esc(k)}" value="">
        </div>`).join('');
    }

    $body.innerHTML = varFields || '<p class="sl-hint">无需填写变量，直接执行</p>';
    $overlay.classList.remove('hidden');
  }

  function closeTestModal() {
    document.getElementById('slTestOverlay')?.classList.add('hidden');
  }

  async function runTest() {
    if (!_editSkill) return;
    const $result = document.getElementById('slTestResult');
    $result.textContent = '（execute_skill 尚未接入云端 AI 引擎，请在 AI 助手中直接 @skill 触发）';
  }

  // ── 事件绑定 ──────────────────────────────────────────────────────────────
  function bindEvents() {
    if ($newBtn) $newBtn.addEventListener('click', openNewModal);
    bindFilters();
    bindNewModal();

    // 编辑 modal
    document.getElementById('slEditCloseBtn')?.addEventListener('click', closeEditModal);
    document.getElementById('slEditOverlay')?.addEventListener('click', e => {
      if (e.target === document.getElementById('slEditOverlay')) closeEditModal();
    });
    document.getElementById('slEditSaveBtn')?.addEventListener('click', saveEditSkill);
    document.getElementById('slEditDeleteBtn')?.addEventListener('click', deleteEditSkill);
    document.getElementById('slEditToggleBtn')?.addEventListener('click', toggleEditSkillStatus);
    document.getElementById('slEditTestBtn')?.addEventListener('click', () => { closeEditModal(); setTimeout(openTestModal, 50); });

    // 测试 modal
    document.getElementById('slTestCloseBtn')?.addEventListener('click', closeTestModal);
    document.getElementById('slTestOverlay')?.addEventListener('click', e => {
      if (e.target === document.getElementById('slTestOverlay')) closeTestModal();
    });
    document.getElementById('slTestCancelBtn')?.addEventListener('click', closeTestModal);
    document.getElementById('slTestRunBtn')?.addEventListener('click', runTest);

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { closeEditModal(); closeTestModal(); closeNewModal(); }
    });
  }

  // ── 启动 ──────────────────────────────────────────────────────────────────
  async function init() {
    bindEvents();
    await loadSkills();
  }

  init();

})();
