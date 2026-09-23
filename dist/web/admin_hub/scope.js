(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AdminHubScope = factory();
}(typeof window !== 'undefined' ? window : globalThis, function () {
  function unwrapCapabilityProjects(response) {
    let value = response;
    // Gateway clients in the web shell may return one or two envelope layers:
    // {data:{success:true,data:[...]}} or {success:true,data:[...]}. Walk only
    // known data/result/value fields and stop as soon as the list is found.
    for (let depth = 0; depth < 5; depth += 1) {
      if (Array.isArray(value)) return value;
      if (!value || typeof value !== 'object') return [];
      if (Array.isArray(value.items)) return value.items;
      if (Array.isArray(value.data)) return value.data;
      const next = value.data ?? value.result ?? value.value;
      if (next === value || next == null) return [];
      value = next;
    }
    return [];
  }

  function buildOrchestrationScope(user, authorizedProject) {
    const tenant_gid = user?.team_gid || user?.team_id || '';
    const project_gid = authorizedProject?.gid || '';
    return tenant_gid && project_gid ? { tenant_gid, project_gid } : null;
  }

  return { unwrapCapabilityProjects, buildOrchestrationScope };
}));
