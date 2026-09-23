(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.AI00SimulationCache = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const DATABASE_NAME = 'ai00-simulation-cache-v1';
  const MAX_BYTES = 200 * 1024 * 1024;
  const STORES = [
    'workspace_heads', 'workspace_generations', 'binding_heads', 'binding_generations',
    'snapshot_summaries', 'diff_summaries',
  ];
  let generationSequence = 0;

  const scopeKey = (subject, workspace) => `${subject}|${workspace}`;
  const bytesOf = value => JSON.stringify(value).length * 2;
  const nowValue = clock => {
    const value = clock();
    return value instanceof Date ? value.getTime() : Number(value);
  };
  const requireId = (value, field) => {
    const text = String(value || '');
    if (!text) throw new TypeError(`${field}_required`);
    return text;
  };
  const isHash = value => /^sha256:[0-9a-f]{64}$/.test(String(value || ''));
  const leaseExpiry = lease => Date.parse(String(lease?.expires_at || ''));
  const lookup = (values, key) => values instanceof Map ? values.get(String(key)) ?? values.get(key)
    : values?.[String(key)];
  const evaluateBinding = (binding, { workspaceNodeVersions, vmDocumentHash, vmNodeFingerprints }) => {
    if (binding.cacheState === 'ambiguous') return { ...binding, canAutoApply: false };
    let staleReason = null;
    let cacheState = 'valid';
    if (binding.vmDocumentIdentityHash !== vmDocumentHash) staleReason = 'vm_document_changed';
    else {
      const workspaceVersion = lookup(workspaceNodeVersions, binding.workspaceNodeGid);
      const vmFingerprint = lookup(vmNodeFingerprints, binding.vmOccurrenceGid);
      if (workspaceVersion == null) {
        cacheState = 'missing_endpoint'; staleReason = 'workspace_node_missing';
      } else if (Number(workspaceVersion) !== Number(binding.workspaceNodeRowVersion)) {
        staleReason = 'workspace_node_changed';
      } else if (vmFingerprint == null) {
        cacheState = 'missing_endpoint'; staleReason = 'vm_node_missing';
      } else if (vmFingerprint !== binding.vmNodeFingerprint) staleReason = 'vm_node_changed';
    }
    if (staleReason && cacheState === 'valid') cacheState = 'stale';
    return { ...binding, cacheState, staleReason, canAutoApply: false };
  };
  const leaseMatches = ({ lease, subject, workspace, rowVersion, cacheRevisionHash, now }) => Boolean(
    lease && String(lease.auth_subject_gid) === subject
    && String(lease.workspace_gid) === workspace
    && Number.isFinite(leaseExpiry(lease)) && leaseExpiry(lease) > now
    && typeof lease.read_lease === 'string' && lease.read_lease.length >= 16
    && (rowVersion == null || Number(lease.row_version) === Number(rowVersion))
    && (cacheRevisionHash == null || lease.cache_revision_hash === cacheRevisionHash)
  );

  const requestResult = request => new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('indexeddb_request_failed'));
  });

  function nativeBackend(indexedDB) {
    if (!indexedDB || typeof indexedDB.open !== 'function') throw new TypeError('indexeddb_required');
    const database = new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE_NAME, 1);
      request.onupgradeneeded = () => STORES.forEach(name => {
        if (!request.result.objectStoreNames.contains(name)) request.result.createObjectStore(name, { keyPath: 'key' });
      });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('indexeddb_open_failed'));
    });
    return {
      async get(store, key) {
        const db = await database;
        return requestResult(db.transaction(store, 'readonly').objectStore(store).get(key));
      },
      async all(store) {
        const db = await database;
        return requestResult(db.transaction(store, 'readonly').objectStore(store).getAll());
      },
      async commit(operations) {
        const db = await database;
        const names = [...new Set(operations.map(operation => operation.store))];
        await new Promise((resolve, reject) => {
          const transaction = db.transaction(names, 'readwrite');
          transaction.oncomplete = () => resolve();
          transaction.onerror = () => reject(transaction.error || new Error('indexeddb_transaction_failed'));
          transaction.onabort = () => reject(transaction.error || new Error('indexeddb_transaction_aborted'));
          operations.forEach(operation => {
            const store = transaction.objectStore(operation.store);
            if (operation.type === 'delete') store.delete(operation.key);
            else store.put(operation.value);
          });
        });
      },
    };
  }

  function createSimulationCache({ indexedDB, clock = () => Date.now(), estimateStorage } = {}) {
    const backend = indexedDB && typeof indexedDB.commit === 'function' ? indexedDB : nativeBackend(indexedDB);
    const estimate = estimateStorage || (typeof navigator !== 'undefined' && navigator.storage?.estimate
      ? () => navigator.storage.estimate() : async () => null);

    async function compact() {
      const storage = await estimate();
      if (!storage || !Number.isFinite(storage.quota) || !Number.isFinite(storage.usage)) return { evicted: 0 };
      const limit = Math.min(MAX_BYTES, Math.floor(storage.quota * 0.2));
      let needed = Math.max(0, storage.usage - limit);
      if (!needed) return { evicted: 0 };
      const now = nowValue(clock);
      const workspaceHeads = await backend.all('workspace_heads');
      const bindingHeads = await backend.all('binding_heads');
      const headKeys = new Set([...workspaceHeads, ...bindingHeads].map(head => head.generationKey));
      const generations = [
        ...(await backend.all('workspace_generations')).map(row => ({ ...row, store: 'workspace_generations' })),
        ...(await backend.all('binding_generations')).map(row => ({ ...row, store: 'binding_generations' })),
      ].sort((left, right) => left.accessedAt - right.accessedAt);
      const operations = [];
      let evicted = 0;
      for (const generation of generations) {
        if (needed <= 0 || headKeys.has(generation.key)) continue;
        operations.push({ type: 'delete', store: generation.store, key: generation.key });
        needed -= generation.byteSize || 0; evicted += 1;
      }
      const expiredHeads = workspaceHeads
        .filter(head => Number(head.leaseExpiresAt || 0) <= now)
        .sort((left, right) => left.accessedAt - right.accessedAt);
      for (const head of expiredHeads) {
        if (needed <= 0) break;
        const generation = generations.find(row => row.key === head.generationKey);
        operations.push(
          { type: 'delete', store: 'workspace_heads', key: head.key },
          { type: 'delete', store: 'workspace_generations', key: head.generationKey },
        );
        needed -= generation?.byteSize || 0; evicted += 1;
      }
      if (operations.length) await backend.commit(operations);
      return { evicted, limitBytes: limit };
    }

    async function commitWithQuotaRetry(operations) {
      try {
        await backend.commit(operations);
      } catch (error) {
        if (error?.name !== 'QuotaExceededError') throw error;
        await compact();
        await backend.commit(operations);
      }
    }

    return {
      async getWorkspace({ authSubjectGid, workspaceGid, lease }) {
        const subject = requireId(authSubjectGid, 'auth_subject_gid');
        const workspace = requireId(workspaceGid, 'workspace_gid');
        const now = nowValue(clock);
        const head = await backend.get('workspace_heads', scopeKey(subject, workspace));
        const effectiveLease = lease || head?.lease;
        if (!head || !leaseMatches({ lease: effectiveLease, subject, workspace, rowVersion: head.rowVersion,
          cacheRevisionHash: head.cacheRevisionHash, now })) return null;
        const generation = await backend.get('workspace_generations', head.generationKey);
        return generation && generation.complete ? generation : null;
      },

      async putWorkspace({ authSubjectGid, workspaceGid, rowVersion, cacheRevisionHash, lease, workspace }) {
        const subject = requireId(authSubjectGid, 'auth_subject_gid');
        const workspaceId = requireId(workspaceGid, 'workspace_gid');
        const now = nowValue(clock);
        if (!Number.isInteger(rowVersion) || rowVersion < 1 || !isHash(cacheRevisionHash)
          || !leaseMatches({ lease, subject, workspace: workspaceId, rowVersion, cacheRevisionHash, now })) {
          throw new TypeError('workspace_cache_generation_invalid');
        }
        const key = `${scopeKey(subject, workspaceId)}|${now}|${++generationSequence}`;
        const generation = { key, authSubjectGid: subject, workspaceGid: workspaceId,
          rowVersion, cacheRevisionHash, workspace, complete: true, createdAt: now, accessedAt: now };
        generation.byteSize = bytesOf(generation);
        const head = { key: scopeKey(subject, workspaceId), authSubjectGid: subject,
          workspaceGid: workspaceId, generationKey: key, rowVersion, cacheRevisionHash,
          lease, leaseExpiresAt: leaseExpiry(lease), accessedAt: now };
        await commitWithQuotaRetry([
          { type: 'put', store: 'workspace_generations', value: generation },
          { type: 'put', store: 'workspace_heads', value: head },
        ]);
        await compact().catch(() => {});
        return generation;
      },

      async getBindings({ authSubjectGid, workspaceGid, workspaceNodeVersions, vmDocumentHash, vmNodeFingerprints }) {
        const key = scopeKey(requireId(authSubjectGid, 'auth_subject_gid'), requireId(workspaceGid, 'workspace_gid'));
        const head = await backend.get('binding_heads', key);
        const generation = head ? await backend.get('binding_generations', head.generationKey) : null;
        if (!generation || workspaceNodeVersions == null || vmDocumentHash == null || vmNodeFingerprints == null) {
          return generation;
        }
        return { ...generation, bindings: generation.bindings.map(binding => evaluateBinding(binding, {
          workspaceNodeVersions, vmDocumentHash, vmNodeFingerprints,
        })) };
      },

      async putBindings({ authSubjectGid, workspaceGid, generation, bindings }) {
        const subject = requireId(authSubjectGid, 'auth_subject_gid');
        const workspace = requireId(workspaceGid, 'workspace_gid');
        const now = nowValue(clock); const key = `${scopeKey(subject, workspace)}|${requireId(generation, 'generation')}`;
        const row = { key, authSubjectGid: subject, workspaceGid: workspace,
          generation, bindings: Array.isArray(bindings) ? bindings : [], complete: true, createdAt: now, accessedAt: now };
        row.byteSize = bytesOf(row);
        await commitWithQuotaRetry([
          { type: 'put', store: 'binding_generations', value: row },
          { type: 'put', store: 'binding_heads', value: { key: scopeKey(subject, workspace), authSubjectGid: subject,
            workspaceGid: workspace, generationKey: key, accessedAt: now } },
        ]);
        return row;
      },

      async putSnapshotSummary({ authSubjectGid, workspaceGid, snapshot }) {
        const subject = requireId(authSubjectGid, 'auth_subject_gid');
        const workspace = requireId(workspaceGid, 'workspace_gid');
        const id = requireId(snapshot?.snapshot_gid, 'snapshot_gid');
        await commitWithQuotaRetry([{ type: 'put', store: 'snapshot_summaries', value: {
          key: `${scopeKey(subject, workspace)}|${id}`, authSubjectGid: subject, workspaceGid: workspace,
          snapshot, accessedAt: nowValue(clock),
        } }]);
      },

      async putDiffSummary({ authSubjectGid, workspaceGid, report }) {
        const subject = requireId(authSubjectGid, 'auth_subject_gid');
        const workspace = requireId(workspaceGid, 'workspace_gid');
        const id = requireId(report?.report_gid, 'report_gid');
        await commitWithQuotaRetry([{ type: 'put', store: 'diff_summaries', value: {
          key: `${scopeKey(subject, workspace)}|${id}`, authSubjectGid: subject, workspaceGid: workspace,
          report, accessedAt: nowValue(clock),
        } }]);
      },

      async clearLocal({ authSubjectGid }) {
        const subject = requireId(authSubjectGid, 'auth_subject_gid');
        const operations = [];
        for (const store of STORES) {
          for (const row of await backend.all(store)) {
            if (row.authSubjectGid === subject) operations.push({ type: 'delete', store, key: row.key });
          }
        }
        if (operations.length) await backend.commit(operations);
      },
      compact,
    };
  }

  return { createSimulationCache };
});
