'use strict';

(function exposeLineageProgressiveLoader(root, factory) {
  const dependencies = typeof module === 'object' && module.exports
    ? {
        LineageLoadCoordinator: require('./lineage_load_coordinator.js').LineageLoadCoordinator,
        LineageProjectionStore: require('./lineage_projection_store.js').LineageProjectionStore,
      }
    : {
        LineageLoadCoordinator: root.LineageLoadCoordinator,
        LineageProjectionStore: root.LineageProjectionStore,
      };
  const api = factory(dependencies);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) {
    root.LineageProgressiveLoader = api.LineageProgressiveLoader;
    root.preloadFirstLineScopes = api.preloadFirstLineScopes;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function createModule(dependencies) {
  const { LineageLoadCoordinator, LineageProjectionStore } = dependencies;

  function preloadFirstLineScopes(lines, loadLine, selectedLineGids = null, options = {}) {
    if (typeof loadLine !== 'function') throw new TypeError('loadLine is required');
    const retryDelays = Array.isArray(options.retryDelays) ? options.retryDelays : [200, 600];
    const sleep = typeof options.sleep === 'function'
      ? options.sleep
      : delay => new Promise(resolve => setTimeout(resolve, delay));
    const transientErrors = new Set([
      'invocation_unavailable',
      'resource_pressure',
      'capacity_unavailable',
      'gateway_unavailable',
    ]);
    const loadWithRetry = async line => {
      for (let attempt = 0; ; attempt += 1) {
        try {
          return await loadLine(line);
        } catch (error) {
          const code = error?.code || error?.message;
          if (!transientErrors.has(code) || attempt >= retryDelays.length) throw error;
          await sleep(retryDelays[attempt]);
        }
      }
    };
    const selected = selectedLineGids == null ? null : new Set(selectedLineGids);
    const visible = (Array.isArray(lines) ? lines : [])
      .filter(line => line?.gid && (!selected || selected.has(line.gid)));
    // Keep first paint bounded; LayoutMode loads other lines when they enter view.
    const initial = selected ? visible : visible.slice(0, 2);
    const results = new Array(initial.length);
    let next = 0;
    const worker = async () => {
      while (next < initial.length) {
        const index = next++;
        try {
          results[index] = { status: 'fulfilled', value: await loadWithRetry(initial[index]) };
        } catch (reason) {
          results[index] = { status: 'rejected', reason };
        }
      }
    };
    return Promise.all(Array.from({ length: Math.min(2, initial.length) }, worker)).then(() => results);
  }

  function isAbort(error) {
    return error?.name === 'AbortError' || error?.code === 'ABORT_ERR';
  }

  function scopeKey(scope) {
    return JSON.stringify([scope.version_gid, scope.revision, scope.scope_kind, scope.scope_gid]);
  }

  class LineageProgressiveLoader {
    constructor(options = {}) {
      if (typeof options.invokeCapability !== 'function') throw new Error('invokeCapability is required');
      this._invokeCapability = options.invokeCapability;
      this._coordinator = options.coordinator || new LineageLoadCoordinator();
      this._store = options.store || new LineageProjectionStore();
      this._versions = new Map();
      this._loadedScopes = new Set();
      this._detailRequests = new Map();
      this._disposed = false;
    }

    _assertActive() {
      if (this._disposed) throw new Error('LineageProgressiveLoader is disposed');
    }

    loadVersion(versionGid, options = {}) {
      this._assertActive();
      if (!versionGid) throw new Error('versionGid is required');
      const key = `${options.force ? 'refresh' : 'load'}:${versionGid}`;
      return this._coordinator.runSingleFlight(key, () => this._loadVersion(versionGid, options));
    }

    async _loadVersion(versionGid, options) {
      const token = this._coordinator.begin(versionGid);
      try {
        const version = await this._invokeCapability(
          'craft.bop.version.get', 1, { version_gid: versionGid }, { signal: token.signal },
        );
        const revision = Number(version?.revision);
        if (!Number.isInteger(revision) || revision < 1) throw new Error('version capability returned an invalid revision');
        if (!this._coordinator.setRevision(token, revision)) return { cancelled: true };

        const roots = new Map();
        const lines = new Map();
        let cursor = null;
        do {
          const payload = { version_gid: versionGid, revision, page_size: 100 };
          if (cursor) payload.cursor = cursor;
          const page = await this._invokeCapability(
            'craft.bop.structure.outline.get', 1, payload, { signal: token.signal },
          );
          if (!this._coordinator.isCurrent(token, revision)) return { cancelled: true };
          if (page?.root?.gid) roots.set(page.root.gid, page.root);
          for (const line of page?.lines || []) if (line?.gid) lines.set(line.gid, line);
          const rows = [...roots.values(), ...lines.values()];
          this._store.replaceOutline({ version_gid: versionGid, revision }, rows);
          const snapshot = {
            cancelled: false,
            token,
            version,
            revision,
            rows,
            root: roots.values().next().value || null,
            lines: [...lines.values()],
            total_lines: page?.total_lines ?? lines.size,
          };
          this._versions.set(versionGid, snapshot);
          if (typeof options.onCommit === 'function') options.onCommit(snapshot);
          cursor = page?.next_cursor || null;
        } while (cursor);
        return this._versions.get(versionGid);
      } catch (error) {
        if (isAbort(error) || !this._coordinator.isCurrent(token)) return { cancelled: true };
        throw error;
      }
    }

    loadScope(scope, options = {}) {
      this._assertActive();
      const state = this._versions.get(scope?.version_gid);
      if (!state || state.revision !== scope?.revision || !this._coordinator.isCurrent(state.token, state.revision)) {
        return Promise.reject(new Error('scope version is not the active generation'));
      }
      return this._coordinator.runSingleFlight(
        `scope:${scopeKey(scope)}`,
        () => this._loadScope(state, scope, options),
      );
    }

    async _loadScope(state, scope, options) {
      let cursor = null;
      do {
        const payload = {
          version_gid: scope.version_gid,
          revision: scope.revision,
          scope_kind: scope.scope_kind,
          scope_gid: scope.scope_gid,
          page_size: 200,
        };
        if (cursor) payload.cursor = cursor;
        const page = await this._invokeCapability(
          'craft.bop.work_package.get', 2, payload, { signal: state.token.signal },
        );
        if (!this._coordinator.isCurrent(state.token, state.revision)) return { cancelled: true };
        this._store.appendScopePage(scope, {
          cursor,
          rows: page?.nodes || [],
          next_cursor: page?.next_cursor || null,
        });
        const value = {
          cancelled: false,
          scope,
          rows: this._store.rowsForActiveScope(scope),
          links: page?.links || [],
          total_count: page?.total_count ?? null,
          next_cursor: page?.next_cursor || null,
        };
        if (typeof options.onPage === 'function') options.onPage(value);
        cursor = page?.next_cursor || null;
      } while (cursor);
      this._loadedScopes.add(scopeKey(scope));
      const completed = { cancelled: false, scope, rows: this._store.rowsForActiveScope(scope) };
      if (typeof options.onComplete === 'function') options.onComplete(completed);
      return completed;
    }

    hasLoadedScope(scope) {
      return !this._disposed && this._loadedScopes.has(scopeKey(scope));
    }

    revisionFor(versionGid) {
      return this._disposed ? null : (this._versions.get(versionGid)?.revision ?? null);
    }

    loadDetail(scope, entryGid, options = {}) {
      this._assertActive();
      const state = this._versions.get(scope?.version_gid);
      if (!state || state.revision !== scope?.revision || !this._coordinator.isCurrent(state.token, state.revision)) {
        return Promise.reject(new Error('detail version is not the active generation'));
      }
      const key = `detail:${scopeKey(scope)}:${entryGid}`;
      return this._coordinator.runSingleFlight(key, async () => {
        const request = {};
        this._detailRequests.set(key, request);
        try {
          const detail = await this._invokeCapability(
            'craft.bop.entry.detail.get',
            1,
            { version_gid: scope.version_gid, revision: scope.revision, entry_gid: entryGid },
            { signal: state.token.signal },
          );
          if (!this._coordinator.isCurrent(state.token, state.revision)
            || this._detailRequests.get(key) !== request) return { cancelled: true };
          if (this._store.rowsForActiveScope(scope).length) this._store.selectDetail(scope, detail);
          return detail;
        } finally {
          if (this._detailRequests.get(key) === request) this._detailRequests.delete(key);
        }
      }, options);
    }

    clearHeavyData() {
      this._assertActive();
      this._store.clearHeavyData();
      this._loadedScopes.clear();
    }

    dispose() {
      if (this._disposed) return;
      this._coordinator.dispose();
      this._store.dispose();
      this._versions.clear();
      this._loadedScopes.clear();
      this._disposed = true;
      this._detailRequests.clear();
    }
  }

  return { LineageProgressiveLoader, preloadFirstLineScopes };
});
