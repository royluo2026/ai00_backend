import { alignOperations, compareRefs } from './compare-engine.js';

const PURPOSES = {
  'base.project.search': '搜索车型项目',
  'craft.bop.version.list': '发现项目 BOP 版本',
  'craft.bop.execution_structure.get': '读取 BOP 层级和线体',
  'craft.bop.work_package.get': '投影线体工艺与资源',
  'craft.bop.linked_parts.get': '补充关联零件详情',
};

export function createTrace() {
  return { items: [] };
}

function publicError(result) {
  const error = new Error(result?.error?.message || result?.error?.code || 'Capability invocation failed');
  error.code = result?.error?.code || 'capability_failed';
  error.retryable = Boolean(result?.error?.retryable);
  return error;
}

function summaryOf(data) {
  if (Array.isArray(data?.items)) return `${data.items.length} 项`;
  if (Array.isArray(data?.nodes)) return `${data.nodes.length} 个节点`;
  if (Array.isArray(data?.work_items)) return `${data.work_items.length} 个操作`;
  return '已获得受控结果';
}

async function invoke(client, capabilityId, payload, trace, purpose = PURPOSES[capabilityId]) {
  const started = Date.now();
  const item = {
    capability_id: capabilityId,
    major: 1,
    purpose: purpose || '读取受控业务材料',
    status: 'running',
    duration_ms: 0,
    summary: '调用中',
  };
  trace.items.push(item);
  try {
    const result = await client.invoke(capabilityId, payload);
    item.duration_ms = Math.max(0, Date.now() - started);
    if (!result?.ok || result.status !== 'completed') throw publicError(result);
    item.status = 'completed';
    item.summary = summaryOf(result.data);
    return result.data;
  } catch (caught) {
    const error = caught?.code ? caught : Object.assign(new Error(caught?.message || 'Capability invocation failed'), { code: 'provider_failed', retryable: false });
    item.duration_ms = Math.max(0, Date.now() - started);
    item.status = 'failed';
    item.summary = error.message;
    item.error_code = error.code;
    throw error;
  }
}

export async function searchProjects(client, query, trace = createTrace()) {
  const data = await invoke(client, 'base.project.search', { query: String(query).trim(), limit: 20 }, trace);
  return data.items || [];
}

export async function loadBopChoices(client, projectRef, trace = createTrace()) {
  const projectGid = String(projectRef || '').replace(/^project:/, '');
  const data = await invoke(client, 'craft.bop.version.list', {
    project_gid: projectGid,
    include_archived: false,
    page_size: 50,
  }, trace);
  return (data.items || []).filter(item => !item.archived);
}

export async function loadBopStructure(client, versionGid, trace = createTrace()) {
  const structure = await invoke(client, 'craft.bop.execution_structure.get', { version_gid: versionGid }, trace);
  const lines = (structure.nodes || []).filter(node => String(node.kind || '').toLowerCase().includes('line'));
  return { structure, lines };
}

export async function loadLineContext(client, versionGid, lineGid, trace = createTrace()) {
  const workPackage = await invoke(client, 'craft.bop.work_package.get', {
    version_gid: versionGid,
    scope: { kind: 'line', gid: lineGid },
  }, trace);
  const parts = await invoke(client, 'craft.bop.linked_parts.get', { version_gid: versionGid }, trace);
  return {
    version_gid: versionGid,
    line_gid: lineGid,
    revision: workPackage.revision,
    operations: workPackage.work_items || [],
    partRefs: workPackage.parts || [],
    toolRefs: workPackage.tools || [],
    linkedParts: parts.items || [],
    workPackage,
  };
}

function partKey(part) {
  return String(part?.part_gid || part?.part_no || part?.name || '');
}

function comparePartDetails(leftParts = [], rightParts = []) {
  const left = new Map(leftParts.map(part => [partKey(part), part]).filter(([key]) => key));
  const right = new Map(rightParts.map(part => [partKey(part), part]).filter(([key]) => key));
  return {
    common: [...left.keys()].filter(key => right.has(key)).sort().map(key => left.get(key)),
    leftOnly: [...left.keys()].filter(key => !right.has(key)).sort().map(key => left.get(key)),
    rightOnly: [...right.keys()].filter(key => !left.has(key)).sort().map(key => right.get(key)),
  };
}

function toolRefs(context) {
  const operationRefs = (context.operations || []).flatMap(operation => operation.resource_refs || []).filter(ref => String(ref).startsWith('tool:'));
  return [...(context.toolRefs || []), ...operationRefs];
}

export function buildComparison(leftContext, rightContext) {
  return {
    alignment: alignOperations(leftContext.operations || [], rightContext.operations || []),
    parts: comparePartDetails(leftContext.linkedParts || [], rightContext.linkedParts || []),
    tools: compareRefs(toolRefs(leftContext), toolRefs(rightContext)),
    left: leftContext,
    right: rightContext,
  };
}

export function partsForOperation(context, operation) {
  const operationId = String(operation?.operation_id || '');
  const refs = new Set((operation?.part_refs || []).map(ref => String(ref).replace(/^part:/, '')));
  return (context?.linkedParts || []).filter(part => (
    refs.has(String(part.part_gid))
    || (part.usage || []).some(use => String(use.entry_gid) === operationId)
  ));
}

export function toolsForOperation(operation) {
  return (operation?.resource_refs || []).filter(ref => String(ref).startsWith('tool:'));
}
