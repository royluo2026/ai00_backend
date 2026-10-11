const CAPABILITY = 'craft.bop.execution_structure.get';
const HASH = /^sha256:[0-9a-f]{64}$/;
const REFERENCE_FIELDS = ['resource_refs', 'model_refs', 'part_refs', 'knowledge_refs', 'rule_refs'];

function validText(value) {
  return typeof value === 'string' && !!value && value.length <= 512;
}

function validList(value, fields) {
  return value === undefined || (Array.isArray(value) && value.length <= 500 &&
    value.every(item => fields ? item && typeof item === 'object' && !Array.isArray(item) &&
      fields.every(field => validText(item[field])) : validText(item)));
}

export function traceExecution(operations, operationId) {
  const byId = new Map(operations.map(operation => [operation.operation_id, operation]));
  if (!byId.has(operationId)) throw new Error('Craft execution operation is invalid');
  const successors = new Map(operations.map(operation => [operation.operation_id, []]));
  for (const operation of operations) {
    for (const predecessor of operation.predecessor_ids) {
      successors.get(predecessor)?.push(operation.operation_id);
    }
  }
  function walk(direction) {
    const seen = new Set([operationId]);
    const queue = [{ id: operationId, distance: 0 }];
    for (let index = 0; index < queue.length; index++) {
      const current = queue[index];
      const neighbors = direction === 'upstream'
        ? byId.get(current.id).predecessor_ids : successors.get(current.id);
      for (const id of neighbors) {
        if (seen.has(id)) continue;
        seen.add(id);
        queue.push({ id, distance: current.distance + 1 });
      }
    }
    return queue.slice(1).map(({ id, distance }) => ({ operation: byId.get(id), distance }))
      .sort((left, right) => left.distance - right.distance ||
        left.operation.sequence - right.operation.sequence ||
        (left.operation.operation_id < right.operation.operation_id ? -1 : 1));
  }
  return { upstream: walk('upstream'), downstream: walk('downstream') };
}

export function executionNeighborhood(operations, operationId) {
  const trace = traceExecution(operations, operationId);
  const candidates = [
    { operation: operations.find(operation => operation.operation_id === operationId), column: 2 },
    ...trace.upstream.filter(entry => entry.distance === 1).map(entry => ({ ...entry, column: 1 })),
    ...trace.downstream.filter(entry => entry.distance === 1).map(entry => ({ ...entry, column: 3 })),
    ...trace.upstream.filter(entry => entry.distance === 2).map(entry => ({ ...entry, column: 0 })),
    ...trace.downstream.filter(entry => entry.distance === 2).map(entry => ({ ...entry, column: 4 })),
  ];
  const visible = candidates.slice(0, 40);
  const ids = new Set(visible.map(entry => entry.operation.operation_id));
  const edges = visible.flatMap(entry => entry.operation.predecessor_ids
    .filter(id => ids.has(id)).map(id => ({ from: id, to: entry.operation.operation_id })));
  return { nodes: visible, edges, omitted: candidates.length - visible.length };
}

export function createCraftExecution(api) {
  async function read(versionGid, revision, projectGid) {
    if (typeof versionGid !== 'string' || !versionGid || versionGid.length > 256 ||
        !Number.isSafeInteger(revision) || revision < 1 ||
        typeof projectGid !== 'string' || !projectGid || projectGid.length > 256) {
      throw new Error('Craft execution request is invalid');
    }
    const response = await api.request(`/api/v1/capabilities/${CAPABILITY}:invoke`, {
      method: 'POST', body: { version: 1, payload: { version_gid: versionGid } },
    });
    if (response?.success !== true || response.data?.ok !== true) {
      throw new Error('Craft execution unavailable');
    }
    const raw = response.data.data;
    const snapshot = raw && Object.keys(raw).length === 1 && raw.data ? raw.data : raw;
    if (snapshot?.source?.bop_version_gid !== versionGid ||
        snapshot.source.revision !== revision || snapshot.source.project_gid !== projectGid) {
      throw new Error('Craft execution identity mismatch');
    }
    if (snapshot.contract_id !== 'craft.execution-plan' || snapshot.contract_version !== 1 ||
        snapshot.official !== true || typeof snapshot.published_at !== 'string' || !snapshot.published_at ||
        !HASH.test(snapshot.content_hash) || !Array.isArray(snapshot.nodes) || snapshot.nodes.length > 2000 ||
        !Array.isArray(snapshot.operations) || !snapshot.operations.length || snapshot.operations.length > 500 ||
        !Array.isArray(snapshot.dependencies) || snapshot.dependencies.length > 2000 ||
        !Array.isArray(snapshot.conditions) || snapshot.conditions.length > 2000) {
      throw new Error('Craft execution snapshot is invalid');
    }
    const byId = new Map();
    for (const [index, operation] of snapshot.operations.entries()) {
      if (!operation || typeof operation.operation_id !== 'string' || !operation.operation_id ||
          operation.operation_id.length > 256 || byId.has(operation.operation_id) ||
          typeof operation.name !== 'string' || !operation.name || operation.name.length > 1024 ||
          !['process', 'operation', 'step'].includes(operation.kind) ||
          !Number.isSafeInteger(operation.sequence) || operation.sequence < 0 ||
          !Array.isArray(operation.predecessor_ids) || operation.predecessor_ids.length > 500 ||
          new Set(operation.predecessor_ids).size !== operation.predecessor_ids.length ||
          REFERENCE_FIELDS.some(field => !validList(operation[field])) ||
          !validList(operation.products, ['product_ref', 'action']) ||
          !validList(operation.resources, ['resource_type', 'code']) ||
          (index > 0 && (snapshot.operations[index - 1].sequence > operation.sequence ||
            (snapshot.operations[index - 1].sequence === operation.sequence &&
              snapshot.operations[index - 1].operation_id >= operation.operation_id)))) {
        throw new Error('Craft execution operation is invalid');
      }
      byId.set(operation.operation_id, operation);
    }
    const expectedEdges = new Set();
    for (const operation of snapshot.operations) {
      for (const predecessor of operation.predecessor_ids) {
        if (typeof predecessor !== 'string' || !byId.has(predecessor) ||
            byId.get(predecessor).sequence >= operation.sequence) {
          throw new Error('Craft execution predecessor is invalid');
        }
        expectedEdges.add(JSON.stringify([predecessor, operation.operation_id]));
        if (expectedEdges.size > 2000) throw new Error('Craft execution dependencies are invalid');
      }
    }
    const actualEdges = new Set();
    for (const edge of snapshot.dependencies) {
      if (!edge || edge.kind !== 'finish_to_start' ||
          typeof edge.from !== 'string' || typeof edge.to !== 'string') {
        throw new Error('Craft execution dependency is invalid');
      }
      actualEdges.add(JSON.stringify([edge.from, edge.to]));
    }
    if (expectedEdges.size !== snapshot.dependencies.length ||
        actualEdges.size !== snapshot.dependencies.length ||
        [...expectedEdges].some(edge => !actualEdges.has(edge))) {
      throw new Error('Craft execution dependencies are invalid');
    }
    return snapshot;
  }

  return { read };
}
