'use strict';
/**
 * BitableSyncManager compatibility shell.
 *
 * The Bitable synchronization backend was retired with the V1 integration
 * service. Keep the UI-facing class so dormant ListShell configuration does
 * not crash, but never issue requests to the removed route family.
 */
class BitableSyncManager {
  constructor({ listGid, columns, getRows, onRemoteUpdate }) {
    this._listGid        = listGid;
    this._columns        = columns || [];
    this._getRows        = getRows || (() => []);
    this._onRemoteUpdate = onRemoteUpdate || (() => {});
    this._binding        = null;
    this._pollTimer      = null;
    this._status         = 'retired';
    this._onStatusChange = null;
    this._feishuFields   = [];
  }

  async init() {
    this._setStatus('retired');
    return false;
  }

  destroy() {
    this._pollTimer = null;
  }

  _setStatus(status) {
    this._status = status;
    if (this._onStatusChange) this._onStatusChange(status);
  }

  async _loadStatus() { return false; }
  async pushRows(_rows) { return false; }
  async pushAll() { return false; }
  async pullAll() { return false; }
  async _fetchBinding() { return null; }
  async unbind() { return false; }

  openBindingModal() {
    alert('飞书多维表格同步已停用。');
    return false;
  }

  openMappingModal() {
    return false;
  }
}
