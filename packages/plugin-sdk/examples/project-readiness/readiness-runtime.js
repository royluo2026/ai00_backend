import { evaluateReadiness, mergeHistory, selectFirstResolved } from './readiness-engine.js';

export const DECLARED_CAPABILITIES = [
  'base.project.search',
  'craft.bop.version.list',
  'craft.bop.execution_structure.get',
  'digital_model.model.search',
  'digital_model.version.get',
  'simulation.run.search',
  'plugin.storage.get',
  'plugin.storage.put',
];

function data(result) {
  if (!result?.ok || result.status !== 'completed') {
    const error = new Error(result?.error?.message || result?.error?.code || 'Capability invocation failed');
    error.code = result?.error?.code || 'capability_failed';
    throw error;
  }
  return result.data;
}

function inaccessible(error) {
  return { status:'inaccessible', error:error?.code || error?.message || String(error) };
}

const INACCESSIBLE_CODES = new Set([
  'permission_denied', 'capability_not_granted', 'mount_expired', 'mount_revoked',
  'provider_failed', 'provider_unavailable', 'network_error', 'request_timeout',
  'host_bridge_failed', 'capability_failed',
]);

export function classifyCandidateFailures(failures) {
  return (failures || []).some(item => INACCESSIBLE_CODES.has(item?.code))
    ? 'inaccessible'
    : 'blocked';
}

function craftCommit(structure, versionGid) {
  const revision = Number(structure?.source?.revision ?? structure?.revision);
  if (!Number.isInteger(revision) || revision < 1) throw new Error('execution structure has no authoritative revision');
  return `craft://bop/version/${versionGid}/execution-structure/r${revision}`;
}

export async function runReadinessCheck(client, project, options = {}) {
  const projectRef = String(project.object_ref || '');
  const projectGid = projectRef.startsWith('project:') ? projectRef.slice(8) : projectRef;
  let craft = { status:'blocked' }; let model = { status:'blocked' }; let runs = [];

  try {
    const versions = data(await client.invoke('craft.bop.version.list', { project_gid:projectGid, include_archived:false, page_size:5 }));
    const candidates = (versions.items || []).filter(item => !item.archived).slice(0, 5);
    const selected = await selectFirstResolved(candidates, async item => {
      const structure = data(await client.invoke('craft.bop.execution_structure.get', { version_gid:item.version_gid }));
      return { structure, craft_commit_ref:structure.craft_commit_ref || craftCommit(structure, item.version_gid) };
    }, 5);
    if (selected.value) craft = { status:'ok', version_gid:selected.candidate.version_gid, craft_commit_ref:selected.value.craft_commit_ref, failures:selected.failures };
    else if (classifyCandidateFailures(selected.failures) === 'inaccessible') {
      craft = inaccessible({ code:selected.failures.at(-1).code });
    }
  } catch (error) { craft = inaccessible(error); }

  try {
    const models = data(await client.invoke('digital_model.model.search', { project_ref:projectRef, limit:5 }));
    const candidates = (models.items || []).filter(item => item.latest_version_id).slice(0, 5);
    const selected = await selectFirstResolved(candidates, async item => data(await client.invoke('digital_model.version.get', { model_id:item.model_id, version_id:item.latest_version_id })), 5);
    if (selected.value) {
      const ref = selected.value.snapshot_ref || selected.value;
      model = { status:'ok', model_id:selected.candidate.model_id, version_id:selected.candidate.latest_version_id, snapshot_hash:ref.snapshot_hash, failures:selected.failures };
    } else if (classifyCandidateFailures(selected.failures) === 'inaccessible') {
      model = inaccessible({ code:selected.failures.at(-1).code });
    }
  } catch (error) { model = inaccessible(error); }

  try { runs = data(await client.invoke('simulation.run.search', { limit:200 })).items || []; }
  catch (error) { runs = inaccessible(error); }

  const evaluated = evaluateReadiness({ project:{ status:'ok', ...project }, craft, model, runs });
  return {
    report_id:options.reportId || crypto.randomUUID(), checked_at:options.now || new Date().toISOString(),
    project:{ object_ref:projectRef, title:project.title || projectRef, summary:project.summary || '' },
    overall_status:evaluated.overall_status, domains:evaluated.domains,
    evidence_refs:{ bop_version_gid:craft.version_gid || null, craft_commit_ref:craft.craft_commit_ref || null, model_id:model.model_id || null, model_version_id:model.version_id || null, model_snapshot_hash:model.snapshot_hash || null, simulation_run_id:evaluated.matched_run?.run_id || null },
    catalog_release:options.catalogRelease || null,
  };
}

async function readHistory(client) {
  const result = await client.storageGet('history/v1');
  if (result?.ok && result.status === 'completed') {
    const stored = result.data?.value;
    const items = Array.isArray(stored) ? stored : (Array.isArray(stored?.items) ? stored.items : []);
    return { items, version:Number(result.data?.version || 0) };
  }
  if (['provider_failed','resource_not_found'].includes(result?.error?.code) || /not found/i.test(result?.error?.message || '')) return { items:[], version:0 };
  data(result);
}

export async function saveHistory(client, report) {
  for (let attempt=0; attempt<2; attempt+=1) {
    const current = await readHistory(client); const next = mergeHistory(current.items, report);
    const result = await client.storagePut(
      'history/v1',
      { schema_version:1, items:next },
      current.version,
    );
    if (result?.ok && result.status === 'completed') return result.data;
    const conflict = result?.error?.code === 'version_conflict'
      || /version conflict/i.test(result?.error?.message || '');
    if (!conflict || attempt === 1) data(result);
  }
  throw new Error('history write failed');
}

export async function loadHistory(client) { return (await readHistory(client)).items; }
