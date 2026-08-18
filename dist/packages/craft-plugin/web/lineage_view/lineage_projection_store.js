'use strict';

(function exposeLineageProjectionStore(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) {
    root.LineageProjectionStore = api.LineageProjectionStore;
    root.lineageUtf8ByteLength = api.utf8ByteLength;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function createModule() {
  function utf8ByteLength(value) {
    const text = typeof value === 'string' ? value : JSON.stringify(value);
    if (typeof TextEncoder === 'function') return new TextEncoder().encode(text).byteLength;
    let bytes = 0;
    for (let index = 0; index < text.length; index += 1) {
      const point = text.codePointAt(index);
      if (point <= 0x7f) bytes += 1;
      else if (point <= 0x7ff) bytes += 2;
      else if (point <= 0xffff) bytes += 3;
      else {
        bytes += 4;
        index += 1;
      }
    }
    return bytes;
  }

  function field(value, snake, camel) {
    return value?.[snake] ?? value?.[camel];
  }

  function versionKey(value) {
    const versionGid = field(value, 'version_gid', 'versionGid');
    const revision = value?.revision;
    if (!versionGid || !Number.isInteger(revision) || revision < 1) {
      throw new Error('version_gid and positive integer revision are required');
    }
    return JSON.stringify([String(versionGid), revision]);
  }

  function scopeKey(value) {
    const scopeKind = field(value, 'scope_kind', 'scopeKind');
    const scopeGid = field(value, 'scope_gid', 'scopeGid');
    if (!scopeKind || !scopeGid) throw new Error('scope_kind and scope_gid are required');
    return JSON.stringify([versionKey(value), String(scopeKind), String(scopeGid)]);
  }

  function positiveLimit(value, name) {
    if (!Number.isInteger(value) || value < 1) throw new Error(`${name} must be a positive integer`);
    return value;
  }

  class LineageProjectionStore {
    constructor(options = {}) {
      this._maxScopes = positiveLimit(options.maxScopes ?? 3, 'maxScopes');
      this._maxNodes = positiveLimit(options.maxNodes ?? 5_000, 'maxNodes');
      this._maxBytes = positiveLimit(options.maxBytes ?? 8 * 1024 * 1024, 'maxBytes');
      this._outlines = new Map();
      this._scopes = new Map();
      this._detail = null;
      this._clock = 0;
      this._disposed = false;
    }

    _assertActive() {
      if (this._disposed) throw new Error('LineageProjectionStore is disposed');
    }

    replaceOutline(version, rows) {
      this._assertActive();
      this._outlines.set(versionKey(version), Array.isArray(rows) ? rows.slice() : []);
    }

    outlineRows(version) {
      if (this._disposed) return [];
      return (this._outlines.get(versionKey(version)) || []).slice();
    }

    appendScopePage(scope, page) {
      this._assertActive();
      const key = scopeKey(scope);
      let entry = this._scopes.get(key);
      if (!entry) {
        entry = { key, pages: new Map(), rows: [], bytes: 0, lastAccess: 0 };
        this._scopes.set(key, entry);
      }
      const cursorKey = page?.cursor == null ? '__first__' : String(page.cursor);
      entry.pages.set(cursorKey, {
        rows: Array.isArray(page?.rows) ? page.rows.slice() : [],
        nextCursor: page?.next_cursor ?? page?.nextCursor ?? null,
      });
      this._rebuild(entry);
      entry.lastAccess = ++this._clock;
      this._enforceLimits();
      return this._scopes.has(key);
    }

    _rebuild(entry) {
      const byGid = new Map();
      const order = [];
      for (const page of entry.pages.values()) {
        for (const row of page.rows) {
          const gid = row?.gid;
          if (!gid) continue;
          if (!byGid.has(gid)) order.push(gid);
          byGid.set(gid, row);
        }
      }
      entry.rows = order.map(gid => byGid.get(gid));
      entry.bytes = utf8ByteLength(entry.rows);
    }

    _totals() {
      let nodes = 0;
      let bytes = 0;
      for (const entry of this._scopes.values()) {
        nodes += entry.rows.length;
        bytes += entry.bytes;
      }
      return { nodes, bytes };
    }

    _enforceLimits() {
      while (this._scopes.size) {
        const totals = this._totals();
        if (
          this._scopes.size <= this._maxScopes
          && totals.nodes <= this._maxNodes
          && totals.bytes <= this._maxBytes
        ) return;
        let oldest = null;
        for (const entry of this._scopes.values()) {
          if (!oldest || entry.lastAccess < oldest.lastAccess) oldest = entry;
        }
        this._scopes.delete(oldest.key);
        if (this._detail?.scopeKey === oldest.key) this._detail = null;
      }
    }

    selectDetail(scope, detail) {
      this._assertActive();
      const key = scopeKey(scope);
      if (!this._scopes.has(key)) throw new Error('detail scope is not cached');
      this.touchScope(scope);
      this._detail = detail == null ? null : { scopeKey: key, value: detail };
    }

    selectedDetail() {
      return this._disposed || !this._detail ? null : this._detail.value;
    }

    touchScope(scope) {
      if (this._disposed) return false;
      const entry = this._scopes.get(scopeKey(scope));
      if (!entry) return false;
      entry.lastAccess = ++this._clock;
      return true;
    }

    rowsForActiveScope(scope) {
      if (this._disposed) return [];
      const key = scopeKey(scope);
      const entry = this._scopes.get(key);
      if (!entry) return [];
      entry.lastAccess = ++this._clock;
      return entry.rows.slice();
    }

    clearHeavyData() {
      if (this._disposed) return;
      this._scopes.clear();
      this._detail = null;
    }

    dispose() {
      this._outlines.clear();
      this._scopes.clear();
      this._detail = null;
      this._disposed = true;
    }
  }

  return { LineageProjectionStore, utf8ByteLength };
});
