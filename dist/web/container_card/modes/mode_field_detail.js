'use strict';
/**
 * mode_field_detail.js — 清单某一格详情展开
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   item_type : 'task' | 'issue' | 'knowledge' | 'rule'
 *   gid       : 条目 gid
 *   field     : 字段 key（如 description / attachments / tags / status / ...）
 *   source    : 'cloud' | 'local'
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['field_detail'] = (() => {

  const ENUM_FIELDS = {
    status:   ['pending','in_progress','blocked','completed','cancelled','open','resolved','closed'],
    priority: ['high','normal','low'],
    severity: ['critical','high','medium','low'],
  };
  const DATE_FIELDS = new Set(['due_date','plan_start','plan_end','actual_start','actual_end']);
  const TEXT_FIELDS = new Set(['description','content','content_md']);
  const _ruleChangeOperations = new Map();
  const _ruleChangeFields = new Set(['name', 'description', 'severity', 'enabled', 'condition', 'message', 'scope', 'tags', 'priority', 'category']);

  async function _saveRuleDefinition(rule, field, value) {
    const reference = rule?.rule_reference;
    const expectedRevision = reference?.rule_revision;
    const ruleGid = reference?.rule_gid;
    if (!ruleGid || !Number.isInteger(expectedRevision)) throw new Error('规则引用未绑定，请刷新后重试');
    const target = field === 'expression' ? 'condition' : field;
    if (!_ruleChangeFields.has(target)) throw new Error(`规则字段不支持受控更新：${field}`);
    const payload = { rule_gid: ruleGid, expected_revision: expectedRevision, changes: { [target]: value } };
    const operationKey = JSON.stringify(payload);
    let operation = _ruleChangeOperations.get(operationKey);
    if (!operation) {
      const idempotencyKey = window.crypto?.randomUUID?.();
      if (!idempotencyKey) throw new Error('无法安全生成规则变更操作标识');
      operation = { idempotencyKey, payload };
      _ruleChangeOperations.set(operationKey, operation);
    }
    if (!window.confirm('确认保存此规则定义变更？')) throw new Error('已取消规则定义变更');
    try {
      const result = await (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient).invoke(
        'craft.rule.definition.change.apply', operation.payload,
        { write: true, confirmed: true, idempotencyKey: operation.idempotencyKey },
      );
      if (result?.status === 'outcome_unknown') throw new Error('规则变更结果未知，请刷新后核对操作结果');
      return result;
    } catch (error) {
      if (error?.code === 'revision_conflict') throw new Error('规则已被更新，请刷新后再试');
      if (error?.code === 'outcome_unknown') throw new Error('规则变更结果未知，请刷新后核对操作结果');
      throw error;
    }
  }

  // ── 加载条目数据 ──────────────────────────────────────────────────────────
  async function _fetchItem(itemType, gid, source, cloudFetch) {
    const _cloudFetch = cloudFetch || window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
    if (!_cloudFetch) return null;
    let resp;
    if (itemType === 'task') resp = await _cloudFetch(`/api/tasks/${gid}`, { method: 'GET' });
    else if (itemType === 'issue') resp = await _cloudFetch(`/api/issues/${gid}`, { method: 'GET' });
    else if (itemType === 'knowledge') resp = await (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient).call('knowledge.get', { gid });
    else if (itemType === 'rule') resp = await _cloudFetch(`/api/rules/${gid}`, { method: 'GET' });
    else throw new Error(`不支持的条目类型: ${itemType}`);
    return resp?.data || resp;
  }

  // ── 保存字段 ─────────────────────────────────────────────────────────────
  async function _saveField(itemType, gid, field, value, source, cloudFetch, currentItem) {
    const _cloudFetch = cloudFetch || window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
    if (!_cloudFetch) return;
    if (itemType === 'task') return _cloudFetch(`/api/tasks/${gid}`, { method: 'PUT', body: JSON.stringify({ [field]: value }) });
    if (itemType === 'issue') return _cloudFetch(`/api/issues/${gid}`, { method: 'PUT', body: JSON.stringify({ [field]: value }) });
    if (itemType === 'knowledge') return (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient).call('knowledge.update', { gid, updates: { [field]: value } });
    if (itemType === 'rule') return _saveRuleDefinition(currentItem, field, value);
    throw new Error(`不支持的条目类型: ${itemType}`);
  }

  // ── 字段值摘要（卡片内显示） ──────────────────────────────────────────────
  function _summary(value, field) {
    if (value === null || value === undefined) return '（空）';
    if (Array.isArray(value)) return `[${value.length} 项]`;
    const s = String(value);
    return s.length > 100 ? s.slice(0, 100) + '…' : s;
  }

  // ── 渲染编辑器（全屏/弹出） ───────────────────────────────────────────────
  function _buildEditor(containerEl, itemType, gid, field, source, cloudFetch, isCard) {
    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;padding:' + (isCard ? '8px' : '16px') + ';gap:8px;';

    const loadingEl = document.createElement('div');
    loadingEl.style.cssText = 'color:var(--text-muted,#999);font-size:13px;padding:8px;';
    loadingEl.textContent = '加载中…';
    containerEl.appendChild(loadingEl);

    _fetchItem(itemType, gid, source, cloudFetch).then(item => {
      loadingEl.remove();
      if (!item) {
        containerEl.innerHTML += '<div style="color:var(--text-danger,#e53e3e);font-size:13px;">加载失败</div>';
        return;
      }

      const fieldValue = item[field];

      // 标题行
      const header = document.createElement('div');
      header.style.cssText = 'font-size:11px;color:var(--text-muted,#999);margin-bottom:4px;';
      header.textContent = `${itemType} · ${gid.slice(0,8)}… · ${field}`;
      containerEl.insertBefore(header, containerEl.firstChild);

      let editorEl, getValue;

      if (field === 'attachments' && Array.isArray(fieldValue)) {
        // 附件列表（只读展示 + 打开）
        const wrap = document.createElement('div');
        wrap.style.cssText = 'flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:6px;';
        if (!fieldValue.length) {
          wrap.innerHTML = '<div style="color:var(--text-muted,#999);font-size:13px;">暂无附件</div>';
        } else {
          fieldValue.forEach(att => {
            const chip = document.createElement('div');
            chip.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:6px;cursor:pointer;font-size:13px;';
            const isImg = att.type === 'image' || /\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(att.url || att.path || '');
            chip.innerHTML = `
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                ${isImg ? '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>' : '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>'}
              </svg>
              <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(att.name || att.url || '附件')}</span>
              <span style="font-size:11px;color:var(--text-muted,#999);">打开</span>
            `;
            chip.addEventListener('click', () => {
              const url = att.url || att.path || '';
              const api = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;
              if (url.startsWith('http')) api?.openExternal?.(url);
              else api?.openPath?.(url);
            });
            wrap.appendChild(chip);
          });
        }
        containerEl.appendChild(wrap);
        return; // 附件只读，不需要保存按钮

      } else if (field === 'tags' && Array.isArray(fieldValue)) {
        // 可编辑标签 chips
        const wrap = document.createElement('div');
        wrap.style.cssText = 'flex:1;display:flex;flex-direction:column;gap:8px;';
        const chipsEl = document.createElement('div');
        chipsEl.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;min-height:32px;padding:6px;border:1px solid var(--border-color,#e5e7eb);border-radius:6px;';
        let tags = [...fieldValue];
        function _renderChips() {
          chipsEl.innerHTML = '';
          tags.forEach((tag, i) => {
            const chip = document.createElement('span');
            chip.style.cssText = 'display:inline-flex;align-items:center;gap:4px;padding:2px 8px;background:var(--bg-accent,#eff6ff);color:var(--accent,#3b82f6);border-radius:12px;font-size:12px;';
            chip.innerHTML = `${_esc(tag)} <span style="cursor:pointer;opacity:.7;font-size:10px;" data-idx="${i}">✕</span>`;
            chip.querySelector('span').addEventListener('click', () => { tags.splice(i, 1); _renderChips(); });
            chipsEl.appendChild(chip);
          });
        }
        _renderChips();
        const addInput = document.createElement('input');
        addInput.type = 'text';
        addInput.placeholder = '输入标签，回车添加…';
        addInput.style.cssText = 'padding:6px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;font-size:13px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);';
        addInput.addEventListener('keydown', e => {
          if (e.key === 'Enter' && addInput.value.trim()) {
            tags.push(addInput.value.trim()); addInput.value = ''; _renderChips();
          }
        });
        wrap.appendChild(chipsEl);
        wrap.appendChild(addInput);
        containerEl.appendChild(wrap);
        getValue = () => tags;

      } else if (ENUM_FIELDS[field]) {
        const sel = document.createElement('select');
        sel.style.cssText = 'padding:6px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;font-size:13px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);';
        ENUM_FIELDS[field].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt; o.textContent = opt;
          if (opt === fieldValue) o.selected = true;
          sel.appendChild(o);
        });
        containerEl.appendChild(sel);
        editorEl = sel;
        getValue = () => sel.value;

      } else if (DATE_FIELDS.has(field)) {
        const inp = document.createElement('input');
        inp.type = 'date';
        inp.value = fieldValue ? String(fieldValue).slice(0, 10) : '';
        inp.style.cssText = 'padding:6px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;font-size:13px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);';
        containerEl.appendChild(inp);
        editorEl = inp;
        getValue = () => inp.value;

      } else if (TEXT_FIELDS.has(field)) {
        // 长文本 — marked.js 渲染 + 编辑切换
        const wrap = document.createElement('div');
        wrap.style.cssText = 'flex:1;display:flex;flex-direction:column;overflow:hidden;gap:6px;';
        const toggleBar = document.createElement('div');
        toggleBar.style.cssText = 'display:flex;gap:6px;flex-shrink:0;';
        const previewBtn = document.createElement('button');
        previewBtn.textContent = '预览';
        previewBtn.style.cssText = 'padding:3px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--accent,#3b82f6);color:#fff;cursor:pointer;font-size:12px;';
        const editBtn = document.createElement('button');
        editBtn.textContent = '编辑';
        editBtn.style.cssText = 'padding:3px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;';
        toggleBar.appendChild(previewBtn); toggleBar.appendChild(editBtn);
        const previewEl = document.createElement('div');
        previewEl.className = 'cc-md-preview';
        previewEl.style.cssText = 'flex:1;overflow-y:auto;padding:8px;background:var(--bg-surface,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:4px;font-size:13px;';
        const editArea = document.createElement('textarea');
        editArea.style.cssText = 'flex:1;padding:8px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;font-size:13px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);resize:none;font-family:monospace;display:none;';
        editArea.value = fieldValue || '';
        function _showPreview() {
          const md = editArea.value || '';
          previewEl.innerHTML = typeof marked !== 'undefined' ? marked.parse(md) : md.replace(/\n/g,'<br>');
          previewEl.style.display = ''; editArea.style.display = 'none';
          previewBtn.style.background = 'var(--accent,#3b82f6)'; previewBtn.style.color = '#fff';
          editBtn.style.background = 'var(--bg-surface,#fff)'; editBtn.style.color = 'var(--text-primary,#333)';
        }
        function _showEdit() {
          previewEl.style.display = 'none'; editArea.style.display = '';
          previewBtn.style.background = 'var(--bg-surface,#fff)'; previewBtn.style.color = 'var(--text-primary,#333)';
          editBtn.style.background = 'var(--accent,#3b82f6)'; editBtn.style.color = '#fff';
        }
        previewBtn.addEventListener('click', _showPreview);
        editBtn.addEventListener('click', _showEdit);
        wrap.appendChild(toggleBar); wrap.appendChild(previewEl); wrap.appendChild(editArea);
        containerEl.appendChild(wrap);
        _showPreview();
        getValue = () => editArea.value;

      } else {
        // 通用文本
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.value = fieldValue !== null && fieldValue !== undefined ? String(fieldValue) : '';
        inp.style.cssText = 'padding:6px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;font-size:13px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);';
        containerEl.appendChild(inp);
        editorEl = inp;
        getValue = () => inp.value;
      }

      // 保存按钮（非附件字段时显示）
      if (getValue) {
        const saveBtn = document.createElement('button');
        saveBtn.textContent = '保存';
        saveBtn.style.cssText = 'align-self:flex-end;padding:6px 20px;border:none;border-radius:4px;background:var(--accent,#3b82f6);color:#fff;cursor:pointer;font-size:13px;flex-shrink:0;';
        let _saving = false;
        saveBtn.addEventListener('click', async () => {
          if (_saving) return;
          _saving = true;
          saveBtn.textContent = '保存中…';
          try {
            const result = await _saveField(itemType, gid, field, getValue(), source, cloudFetch, item);
            if (itemType === 'rule' && Number.isInteger(result?.revision)) {
              item.revision = result.revision;
              item.rule_reference = { rule_gid: result.rule_gid || item.gid, rule_revision: result.revision };
            }
            saveBtn.textContent = '已保存';
            setTimeout(() => { saveBtn.textContent = '保存'; _saving = false; }, 1500);
          } catch (err) {
            saveBtn.textContent = err?.message || '保存失败';
            setTimeout(() => { saveBtn.textContent = '保存'; _saving = false; }, 2000);
          }
        });
        containerEl.appendChild(saveBtn);
      }
    });
  }

  // ── 全屏渲染 ─────────────────────────────────────────────────────────────
  function renderFullPage(containerEl, urlParams) {
    const itemType = urlParams.item_type || 'task';
    const gid      = urlParams.gid || '';
    const field    = urlParams.field || 'description';
    const source   = urlParams.source || 'local';
    const cloudFetch = typeof _cf === 'function' ? _cf() : null;

    containerEl.style.cssText = 'height:100%;overflow:hidden;';
    _buildEditor(containerEl, itemType, gid, field, source, cloudFetch, false);
  }

  // ── 卡片渲染 ─────────────────────────────────────────────────────────────
  function renderInCard(containerEl, params, ctx) {
    const itemType = params.item_type || 'task';
    const gid      = params.gid || '';
    const field    = params.field || 'description';
    const source   = params.source || 'local';
    const cloudFetch = ctx?.cloudFetch || null;

    if (!gid) {
      containerEl.innerHTML = '<div style="padding:12px;color:var(--text-muted,#999);font-size:13px;">未配置条目 GID</div>';
      return null;
    }

    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    // 加载摘要显示
    _fetchItem(itemType, gid, source, cloudFetch).then(item => {
      const val = item?.[field];
      const summary = _summary(val, field);

      containerEl.innerHTML = '';
      containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;padding:10px;gap:6px;';
      const label = document.createElement('div');
      label.style.cssText = 'font-size:11px;color:var(--text-muted,#999);';
      label.textContent = `${itemType} · ${field}`;
      const content = document.createElement('div');
      content.style.cssText = 'flex:1;overflow:hidden;font-size:13px;color:var(--text-primary,#333);white-space:pre-wrap;word-break:break-word;';
      content.textContent = summary;
      const expandBtn = document.createElement('button');
      expandBtn.textContent = '展开编辑';
      expandBtn.style.cssText = 'align-self:flex-end;padding:4px 12px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;flex-shrink:0;';
      expandBtn.addEventListener('click', () => {
        if (typeof window._ccPopOut === 'function') window._ccPopOut('field_detail', params);
      });
      containerEl.appendChild(label); containerEl.appendChild(content); containerEl.appendChild(expandBtn);
    }).catch(() => {
      containerEl.innerHTML = '<div style="padding:8px;color:var(--text-muted,#999);font-size:13px;">加载失败</div>';
    });

    return null;
  }

  function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { renderInCard, renderFullPage };
})();
