export async function selectFirstResolved(candidates, resolve, limit = 5) {
  const failures = [];
  for (const candidate of (candidates || []).slice(0, limit)) {
    try {
      return { candidate, value: await resolve(candidate), failures };
    } catch (error) {
      failures.push({
        candidate,
        code: error?.code || 'candidate_failed',
        error: error?.message || String(error),
      });
    }
  }
  return { candidate: null, value: null, failures };
}

function domain(status, detail = {}) {
  return { status, ...detail };
}

export function evaluateReadiness({ project, craft, model, runs }) {
  const runList = Array.isArray(runs) ? runs : [];
  const domains = {
    project: project || domain('blocked'),
    craft: craft || domain('blocked'),
    digital_model: model || domain('blocked'),
    simulation: Array.isArray(runs) ? domain('ok', { total: runList.length }) : (runs || domain('blocked')),
  };
  const inaccessible = Object.values(domains).some(item => item?.status === 'inaccessible');
  if (inaccessible) return { overall_status: 'inaccessible', matched_run: null, domains };
  if (project?.status !== 'ok' || craft?.status !== 'ok' || model?.status !== 'ok') {
    return { overall_status: 'blocked', matched_run: null, domains };
  }
  const matching = runList.filter(run => run.craft_commit_ref === craft.craft_commit_ref && run.model_snapshot_hash === model.snapshot_hash);
  const completed = matching.find(run => run.status === 'completed');
  if (completed) return { overall_status: 'ready', matched_run: completed, domains: { ...domains, simulation: domain('ok', { total:runList.length, matching:matching.length }) } };
  const actionable = matching.filter(run => ['queued', 'running', 'failed'].includes(run.status));
  if (actionable.length) return { overall_status: 'attention', matched_run: actionable[0], domains: { ...domains, simulation: domain('attention', { total:runList.length, matching:actionable.length }) } };
  return { overall_status: 'blocked', matched_run: null, domains: { ...domains, simulation: domain('blocked', { total:runList.length, matching:0 }) } };
}

export function mergeHistory(existing, report) {
  const next = [report, ...(Array.isArray(existing) ? existing : []).filter(item => item?.report_id !== report?.report_id)];
  return next.slice(0, 20);
}
