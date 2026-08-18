'use strict';

(function exposeLineageLoadCoordinator(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LineageLoadCoordinator = api.LineageLoadCoordinator;
})(typeof globalThis !== 'undefined' ? globalThis : this, function createModule() {
  class LineageLoadCoordinator {
    constructor(options = {}) {
      this._AbortController = options.AbortController || globalThis.AbortController;
      if (typeof this._AbortController !== 'function') {
        throw new Error('AbortController is required');
      }
      this._generation = 0;
      this._active = null;
      this._singleFlights = new Map();
      this._disposed = false;
    }

    begin(versionGid) {
      if (this._disposed) throw new Error('LineageLoadCoordinator is disposed');
      if (this._active && !this._active.signal.aborted) this._active.controller.abort();
      const controller = new this._AbortController();
      const token = {
        generation: ++this._generation,
        versionGid,
        revision: null,
        signal: controller.signal,
        controller,
      };
      this._active = token;
      return token;
    }

    setRevision(token, revision) {
      if (!this.isCurrent(token)) return false;
      token.revision = revision;
      return true;
    }

    isCurrent(token, revision) {
      if (this._disposed || !token || token !== this._active || token.signal.aborted) return false;
      return revision === undefined || token.revision === revision;
    }

    runSingleFlight(key, fn) {
      if (this._disposed) return Promise.reject(new Error('LineageLoadCoordinator is disposed'));
      const existing = this._singleFlights.get(key);
      if (existing) return existing;

      let operation;
      try {
        operation = Promise.resolve(fn());
      } catch (error) {
        operation = Promise.reject(error);
      }
      const tracked = operation.finally(() => {
        if (this._singleFlights.get(key) === tracked) this._singleFlights.delete(key);
      });
      this._singleFlights.set(key, tracked);
      return tracked;
    }

    dispose() {
      if (this._active && !this._active.signal.aborted) this._active.controller.abort();
      this._active = null;
      this._singleFlights.clear();
      this._disposed = true;
    }
  }

  return { LineageLoadCoordinator };
});
