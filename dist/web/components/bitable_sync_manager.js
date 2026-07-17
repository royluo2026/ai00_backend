'use strict';
/**
 * BitableSyncManager — 飞书多维表格双向同步管理器
 *
 * 使用方式：
 *   const mgr = new BitableSyncManager({
 *     listGid: 'xxx',
 *     columns: COLUMNS,
 *     getRows: () => _allRows,
 *     onRemoteUpdate: () => load(),
 *   });
 *   await mgr.init();
 *   mgr.destroy();
 */
class BitableSyncManager {
  constructor({ listGid, columns, getRows, onRemoteUpdate }) {
    this._listGid        = listGid;
    this._columns        = columns || [];
    this._getRows        = getRows || (() => []);
    this._onRemoteUpdate = onRemoteUpdate || (() => {});
    this._binding        = null;
    this._pollTimer      = null;
    this._status         = 'unbound'; // unbound | synced | pending | error
    this._onStatusChange = null;
    this._feishuFields   = [];
  }

  // ── 初始化 ──────────────────────────────────────────────────────────────────

  async init() {
    await this._loadStatus();
    this._startPoll();
  }

  destroy() {
    if (this._pollTimer) clearInterval(this._pollTimer);
    this._pollTimer = null;
  }

  // ── 状态轮询 ─────────────────────────────────────────────────────────────────

  _startPoll() {
    if (this._pollTimer) clearInterval(this._pollTimer);
    this._pollTimer = setInterval(() => this._loadStatus(), 30000);
  }

  async _loadStatus() {
    if (!this._listGid) return;
    try {
      const res = await window._cloudFetch(`/api/bitable-sync/bindings/${this._listGid}/status`);
      if (!res.success) return;
      const d = res.data;
      if (!d.bound) {
        this._binding = null;
        this._setStatus('unbound');
        return;
      }
      if (d.has_remote_updates) {
        this._setStatus('pending');
        this._onRemoteUpdate();
      } else {
        this._setStatus('synced');
      }
    } catch (e) {
      this._setStatus('error');
    }
  }

  _setStatus(s) {
    this._status = s;
    if (this._onStatusChange) this._onStatusChange(s);
  }

  // ── 推送 ────────────────────────────────────────────────────────────────────

  async pushRows(rows) {
    if (!this._listGid || !rows || !rows.length) return;
    try {
      await window._cloudFetch('/api/bitable-sync/rows/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ list_gid: this._listGid, rows }),
      });
      this._setStatus('synced');
    } catch (e) {
      this._setStatus('error');
    }
  }

  async pushAll() {
    const rows = this._getRows();
    try {
      this._setStatus('pending');
      await window._cloudFetch(`/api/bitable-sync/bindings/${this._listGid}/push`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      });
      this._setStatus('synced');
    } catch (e) {
      this._setStatus('error');
      throw e;
    }
  }

  async pullAll() {
    try {
      this._setStatus('pending');
      await window._cloudFetch(`/api/bitable-sync/bindings/${this._listGid}/pull`, {
        method: 'POST',
      });
      this._onRemoteUpdate();
      this._setStatus('synced');
    } catch (e) {
      this._setStatus('error');
      throw e;
    }
  }

  // ── 绑定配置弹窗 (Step 1) ────────────────────────────────────────────────────

  async openBindingModal() {
    const existing = await this._fetchBinding();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay bsm-overlay';
    overlay.innerHTML = `
      <div class="modal-box bsm-modal" style="width:420px">
        <div class="modal-header">
          <span>绑定飞书多维表格</span>
          <button class="modal-close-btn" id="bsmClose">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="modal-body" style="display:flex;flex-direction:column;gap:12px;padding:16px">
          <label style="font-size:13px;color:var(--text-secondary)">App Token</label>
          <input id="bsmAppToken" class="form-input" placeholder="例：bascnXxxYyy" value="${existing?.app_token || ''}">
          <label style="font-size:13px;color:var(--text-secondary)">Table ID</label>
          <input id="bsmTableId" class="form-input" placeholder="例：tblXxxYyy" value="${existing?.table_id || ''}">
          <div id="bsmVerifyMsg" style="font-size:12px;color:var(--text-secondary)"></div>
        </div>
        <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 16px">
          <button class="btn-ghost" id="bsmCancel">取消</button>
          <button class="btn-primary" id="bsmVerify">验证并获取字段<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-left:4px"><polyline points="9 18 15 12 9 6"/></svg></button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#bsmClose').onclick = close;
    overlay.querySelector('#bsmCancel').onclick = close;
    overlay.querySelector('#bsmVerify').onclick = async () => {
      const appToken = overlay.querySelector('#bsmAppToken').value.trim();
      const tableId  = overlay.querySelector('#bsmTableId').value.trim();
      const msg      = overlay.querySelector('#bsmVerifyMsg');
      if (!appToken || !tableId) {
        msg.textContent = '请填写 App Token 和 Table ID';
        return;
      }
      msg.textContent = '验证中…';
      try {
        const res = await window._cloudFetch(
          `/api/bitable-sync/bindings/${this._listGid}/schema-by-token?app_token=${encodeURIComponent(appToken)}&table_id=${encodeURIComponent(tableId)}`
        );
        if (!res.success) throw new Error(res.error || '验证失败');
        this._feishuFields = res.data || [];
        msg.style.color = 'var(--accent-green, #3cb371)';
        msg.textContent = `验证成功，共 ${this._feishuFields.length} 个字段`;
        setTimeout(() => {
          close();
          this.openMappingModal(appToken, tableId, existing?.field_mapping || {});
        }, 600);
      } catch (e) {
        msg.style.color = 'var(--danger, #e06c75)';
        msg.textContent = `验证失败：${e.message}`;
      }
    };
  }

  // ── 字段映射器弹窗 (Step 2) ──────────────────────────────────────────────────

  async openMappingModal(appToken, tableId, existingMapping) {
    const rows = this._columns
      .filter(c => c.field && c.field !== 'gid')
      .map(c => {
        const mapped = existingMapping[c.field] || '';
        const autoMatch = this._feishuFields.find(
          f => f.field_name === c.label || f.field_name === c.field
        );
        const selected = mapped || (autoMatch ? autoMatch.field_id : '');
        const opts = this._feishuFields.map(f =>
          `<option value="${f.field_id}" ${f.field_id === selected ? 'selected' : ''}>${f.field_name}</option>`
        ).join('');
        return `
          <tr>
            <td style="padding:6px 8px;font-size:13px">${c.label || c.field} <span style="opacity:.5;font-size:11px">(${c.field})</span></td>
            <td style="padding:6px 8px">
              <select class="bsm-field-sel form-select" data-ai00="${c.field}" style="width:100%;font-size:13px">
                <option value="">（不同步）</option>
                ${opts}
              </select>
            </td>
          </tr>`;
      }).join('');

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay bsm-overlay';
    overlay.innerHTML = `
      <div class="modal-box bsm-modal" style="width:500px;max-height:80vh;display:flex;flex-direction:column">
        <div class="modal-header">
          <span>字段映射配置</span>
          <button class="modal-close-btn" id="bsmMapClose">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div style="overflow-y:auto;flex:1">
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="background:var(--bg-secondary);font-size:12px;color:var(--text-secondary)">
                <th style="padding:6px 8px;text-align:left">AI00 列</th>
                <th style="padding:6px 8px;text-align:left">飞书字段</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 16px">
          <button class="btn-ghost" id="bsmMapCancel">取消</button>
          <button class="btn-primary" id="bsmMapSave">保存绑定</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#bsmMapClose').onclick = close;
    overlay.querySelector('#bsmMapCancel').onclick = close;
    overlay.querySelector('#bsmMapSave').onclick = async () => {
      const mapping = {};
      overlay.querySelectorAll('.bsm-field-sel').forEach(sel => {
        if (sel.value) mapping[sel.dataset.ai00] = sel.value;
      });
      try {
        await window._cloudFetch(`/api/bitable-sync/bindings/${this._listGid}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ app_token: appToken, table_id: tableId, field_mapping: mapping }),
        });
        close();
        await this._loadStatus();
        this._setStatus('synced');
      } catch (e) {
        alert('保存失败: ' + e.message);
      }
    };
  }

  async _fetchBinding() {
    try {
      const res = await window._cloudFetch(`/api/bitable-sync/bindings/${this._listGid}`);
      return res.success ? res.data : null;
    } catch { return null; }
  }

  // ── 解除绑定 ─────────────────────────────────────────────────────────────────

  async unbind() {
    if (!confirm('确认解除与飞书多维表格的绑定？')) return;
    await window._cloudFetch(`/api/bitable-sync/bindings/${this._listGid}`, { method: 'DELETE' });
    this._binding = null;
    this._setStatus('unbound');
  }
}

