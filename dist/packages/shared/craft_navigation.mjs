const OUTLINE = 'craft.bop.structure.outline.get';
const ENTRY_DETAIL = 'craft.bop.entry.detail.get';
const WORK_PACKAGE = 'craft.bop.work_package.get';
const COUNT_FIELDS = ['stations', 'roles', 'processes', 'operations', 'parts', 'resources'];

function revisionNumber(value) {
  const revision = typeof value === 'string' && /^[1-9]\d*$/.test(value) ? Number(value) : value;
  if (!Number.isSafeInteger(revision) || revision < 1) throw new Error('Craft revision is invalid');
  return revision;
}

export function createCraftNavigation(invokeCapability) {
  async function invoke(capabilityId, payload, version = 1) {
    const response = await invokeCapability(capabilityId, { version, payload });
    if (response?.success !== true || response.data?.ok !== true) {
      throw new Error(response?.data?.error?.code || 'Craft navigation unavailable');
    }
    const result = response.data.data;
    if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error('Craft navigation response is invalid');
    return Object.keys(result).length === 1 && result.data && typeof result.data === 'object'
      ? result.data : result;
  }

  function validateIdentity(versionGid, revision, result) {
    if (result.version_gid !== versionGid || result.revision !== revision) {
      throw new Error('Craft navigation identity mismatch');
    }
  }

  async function outline(versionGid, revisionValue, cursor) {
    if (typeof versionGid !== 'string' || !versionGid || versionGid.length > 256 ||
        (cursor !== undefined && (typeof cursor !== 'string' || !cursor))) {
      throw new Error('Craft outline request is invalid');
    }
    const revision = revisionNumber(revisionValue);
    const result = await invoke(OUTLINE, {
      version_gid: versionGid, revision, page_size: 50, ...(cursor ? { cursor } : {}),
    });
    validateIdentity(versionGid, revision, result);
    if (!Array.isArray(result.lines) || result.lines.length > 50 ||
        !Number.isSafeInteger(result.total_lines) || result.total_lines < 0 ||
        (result.next_cursor !== null && (typeof result.next_cursor !== 'string' || !result.next_cursor)) ||
        result.lines.some(line => !line || typeof line.gid !== 'string' || !line.gid ||
          (line.title !== null && typeof line.title !== 'string') ||
          !line.counts || COUNT_FIELDS.some(field => !Number.isSafeInteger(line.counts[field]) || line.counts[field] < 0))) {
      throw new Error('Craft outline page is invalid');
    }
    return result;
  }

  async function entryDetail(versionGid, revisionValue, entryGid) {
    if (typeof versionGid !== 'string' || !versionGid || versionGid.length > 256 ||
        typeof entryGid !== 'string' || !entryGid || entryGid.length > 256) {
      throw new Error('Craft entry request is invalid');
    }
    const revision = revisionNumber(revisionValue);
    const result = await invoke(ENTRY_DETAIL, { version_gid: versionGid, revision, entry_gid: entryGid });
    validateIdentity(versionGid, revision, result);
    if (result.entry?.gid !== entryGid || result.entry?.version_gid !== versionGid ||
        typeof result.entry.node_type !== 'string' || !result.entry.node_type ||
        ['title', 'vpps', 'vpps_desc', 'parent_gid', 'owner_gid', 'created_at', 'updated_at']
          .some(field => result.entry[field] !== undefined && result.entry[field] !== null &&
            typeof result.entry[field] !== 'string') ||
        !Array.isArray(result.links) || result.links.length > 500 ||
        result.links.some(link => !link || typeof link !== 'object' || Array.isArray(link) ||
          typeof link.link_gid !== 'string' || !link.link_gid ||
          link.entry_gid !== entryGid || link.version_gid !== versionGid ||
          typeof link.link_type !== 'string' || !link.link_type ||
          typeof link.entity_gid !== 'string' || !link.entity_gid ||
          (link.entity_title !== undefined && link.entity_title !== null && typeof link.entity_title !== 'string') ||
          (link.entity_part_no !== undefined && link.entity_part_no !== null && typeof link.entity_part_no !== 'string'))) {
      throw new Error('Craft entry identity mismatch');
    }
    return result;
  }

  async function workPackage(versionGid, revisionValue, scopeKind, scopeGid, cursor) {
    if (typeof versionGid !== 'string' || !versionGid || versionGid.length > 256 ||
        !['line', 'station'].includes(scopeKind) ||
        typeof scopeGid !== 'string' || !scopeGid || scopeGid.length > 256 ||
        (cursor !== undefined && (typeof cursor !== 'string' || !cursor))) {
      throw new Error('Craft work package request is invalid');
    }
    const revision = revisionNumber(revisionValue);
    const result = await invoke(WORK_PACKAGE, {
      version_gid: versionGid, revision, scope_kind: scopeKind, scope_gid: scopeGid,
      page_size: 50, ...(cursor ? { cursor } : {}),
    }, 2);
    validateIdentity(versionGid, revision, result);
    if (result.scope?.kind !== scopeKind || result.scope.gid !== scopeGid ||
        !Array.isArray(result.nodes) || result.nodes.length > 50 ||
        !Array.isArray(result.links) ||
        !Number.isSafeInteger(result.total_count) || result.total_count < 0 ||
        (result.next_cursor !== null && (typeof result.next_cursor !== 'string' || !result.next_cursor)) ||
        result.nodes.some(node => !node || typeof node.gid !== 'string' || !node.gid ||
          typeof node.node_type !== 'string' ||
          (node.parent_gid !== undefined && node.parent_gid !== null &&
            (typeof node.parent_gid !== 'string' || !node.parent_gid)) ||
          (node.title !== null && typeof node.title !== 'string') ||
          (node.vpps !== null && typeof node.vpps !== 'string'))) {
      throw new Error('Craft work package page is invalid');
    }
    return result;
  }

  return { outline, workPackage, entryDetail, revisionNumber };
}
