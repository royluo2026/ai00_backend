(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.AI00ExistingCapabilityClient = api.createExistingCapabilityClient();
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const operationTargets = Object.freeze({
    'knowledge.search': 'knowledge.search',
    'knowledge.get': 'knowledge.get',
    'knowledge.create': 'knowledge.entry.change.apply.atomic.entries_create',
    'knowledge.update': 'knowledge.entry.change.apply.atomic.entries_update',
    'knowledge.delete': 'knowledge.entry.change.apply.atomic.entries_delete',
    'project.task.update': 'project.task.change.apply.atomic.tasks_update',
    'project.issue.update': 'project.issue.change.apply.atomic.issues_update',
    'project.itemEntries.get': 'project.list.read.atomic.item_entries_get',
    'project.itemEntries.replace': 'project.list.change.apply.atomic.item_entries_replace',
    'base.grants.list': 'base.authorization.grant.list',
    'base.grants.create': 'base.authorization.grant.create',
    'base.grants.revoke': 'base.authorization.grant.revoke',
    'base.notifications.preferences.get': 'base.notification.preference.atomic.get',
    'base.notifications.preferences.update': 'base.notification.preference.atomic.update',
    'base.directory.feishu.sync': 'base.identity.directory.feishu.sync',
    'base.plugins.list': 'base.plugin.installed.list',
    'base.plugins.install': 'base.plugin.installation.request.create',
    'base.plugins.uninstall': 'base.plugin.installation.transition.uninstall',
    'base.users.search': 'base.identity.user.search',
    'base.orgTeams.list': 'base.organization.team.directory.list',
    'base.teams.list': 'base.team.directory.list',
    'base.annotations.batch': 'base.self_annotation.batch.get',
    'base.annotations.get': 'base.self_annotation.record.get',
    'base.annotations.search': 'base.self_annotation.search',
    'base.annotations.apply': 'base.self_annotation.change.apply',
    'base.identity.session.profile.get': 'base.identity.session.profile.get',
    'base.users.list': 'base.identity.admin_user.list',
    'base.users.assignRole': 'base.identity.role.assign.atomic',
    'base.fileStore.publicConfig.get': 'base.file_store.public_config.get',
    'base.savedViews.search': 'base.saved_view.search',
    'base.savedViews.create': 'base.saved_view.create',
    'base.savedViews.update': 'base.saved_view.update',
    'base.savedViews.copy': 'base.saved_view.copy',
    'base.savedViews.delete': 'base.saved_view.delete',
  });

  const LIST_CAPABILITIES = Object.freeze({
    bop_version: Object.freeze({ search: 'craft.bop.version.list', delete: 'craft.bop.version.archive' }),
    project: Object.freeze({ search: 'project.list.read.atomic.lists_search', delete: 'project.list.change.apply.atomic.lists_delete' }),
  });
  const projectListTypes = new Set([null, '', 'task', 'issue', 'knowledge', 'rule']);

  function capabilityNotBound(itemType) {
    const error = new TypeError(`capability_not_bound:${itemType ?? 'null'}`);
    error.code = 'capability_not_bound';
    return error;
  }

  function resolveListCapability({ operation, itemType = null } = {}) {
    const family = itemType === 'bop_version'
      ? 'bop_version'
      : projectListTypes.has(itemType) ? 'project' : null;
    const capabilityId = family && LIST_CAPABILITIES[family][operation];
    if (!capabilityId) throw capabilityNotBound(itemType);
    return { capabilityId, write: operation === 'delete' };
  }

  function listSearch({ itemType = null, ownerTeamGid = null, query = null } = {}) {
    const resolved = resolveListCapability({ operation: 'search', itemType });
    if (itemType === 'bop_version') return {
      ...resolved,
      payload: { ...(query ? { query } : {}) },
      legacy: value => ({ success: true, data: value?.items || [] }),
    };
    return {
      ...resolved,
      payload: { arguments: { item_type: itemType || null, owner_team_gid: ownerTeamGid, q: query } },
      legacy: value => value,
    };
  }

  function listPatch({ gid, patch, itemType = null, expectedRevision } = {}) {
    if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new TypeError('清单更新必须提供对象');
    if (patch.archive === true) {
      return listDelete({ gid, itemType, expectedRevision });
    }
    if (patch.archive !== undefined && patch.archive !== false) throw new TypeError('不支持的清单更新分派');
    const { archive: _archive, ...updates } = patch;
    return {
      capabilityId: 'project.list.change.apply.atomic.lists_update', write: true,
      payload: { arguments: { gid, updates } }, legacy: value => value,
    };
  }

  function listDelete({ gid, itemType = null, expectedRevision } = {}) {
    const resolved = resolveListCapability({ operation: 'delete', itemType });
    if (!Number.isInteger(expectedRevision)) throw new TypeError('清单删除需要整数 expectedRevision');
    return {
      ...resolved,
      confirmation: 'user',
      idempotencyKeyRequired: true,
      payload: itemType === 'bop_version'
        ? { version_gid: gid, expected_revision: expectedRevision }
        : { arguments: { gid, expected_revision: expectedRevision } },
      legacy: value => value,
    };
  }

  const operations = {
    'knowledge.search': {
      capabilityId: operationTargets['knowledge.search'],
      payload: ({ listGid }) => ({ query: '', ...(listGid ? { list_gid: listGid } : {}), include_content: true, limit: 200 }),
      legacy: value => ({ success: true, data: value?.items || [] }),
    },
    'knowledge.get': {
      capabilityId: operationTargets['knowledge.get'],
      payload: ({ gid }) => ({ gid }),
      legacy: value => ({ success: true, data: value }),
    },
    'knowledge.create': {
      capabilityId: operationTargets['knowledge.create'],
      write: true,
      payload: ({ record }) => record,
      legacy: value => ({ success: true, data: value }),
    },
    'knowledge.update': {
      capabilityId: operationTargets['knowledge.update'],
      write: true,
      payload: ({ gid, updates }) => ({ gid, updates }),
      legacy: () => ({ success: true }),
    },
    'knowledge.delete': {
      capabilityId: operationTargets['knowledge.delete'],
      write: true,
      payload: ({ gid }) => ({ gid }),
      legacy: () => ({ success: true }),
    },
    'project.task.update': projectUpdate(operationTargets['project.task.update']),
    'project.issue.update': projectUpdate(operationTargets['project.issue.update']),
    'project.itemEntries.get': {
      capabilityId: operationTargets['project.itemEntries.get'],
      payload: ({ itemGid }) => ({ arguments: { item_type: 'task', item_gid: itemGid } }),
      legacy: value => ({ success: true, data: value?.entries || [] }),
    },
    'project.itemEntries.replace': {
      capabilityId: operationTargets['project.itemEntries.replace'],
      write: true,
      payload: ({ itemGid, entries }) => ({ arguments: { item_type: 'task', item_gid: itemGid, entries } }),
      legacy: value => ({ success: true, data: value }),
    },
    'base.grants.list': exactOutcome(operationTargets['base.grants.list'], ({ userGid = null }) => ({ user_gid: userGid })),
    'base.grants.create': exactOutcome(operationTargets['base.grants.create'], ({ granteeGid, grantType, scopeGid = null, expiresAt = null, note = '' }) => ({ grantee_gid: granteeGid, grant_type: grantType, scope_gid: scopeGid, expires_at: expiresAt, note }), true),
    'base.grants.revoke': exactOutcome(operationTargets['base.grants.revoke'], ({ gid }) => ({ gid }), true),
    'base.notifications.preferences.get': exactOutcome(operationTargets['base.notifications.preferences.get'], () => ({})),
    'base.notifications.preferences.update': exactOutcome(operationTargets['base.notifications.preferences.update'], ({ preferences }) => ({ preferences }), true),
    'base.directory.feishu.sync': exactOutcome(operationTargets['base.directory.feishu.sync'], ({ departmentId = null }) => ({ department_id: departmentId }), true),
    'base.plugins.list': exactOutcome(operationTargets['base.plugins.list'], () => ({})),
    'base.plugins.install': pluginLifecycleWrite(
      operationTargets['base.plugins.install'],
      ({ pluginId, releaseVersion, releaseSha256, requestedGrants }) => ({
        plugin_id: pluginId, release_version: releaseVersion, release_sha256: releaseSha256,
        requested_grants: requestedGrants,
      }),
    ),
    'base.plugins.uninstall': pluginLifecycleWrite(
      operationTargets['base.plugins.uninstall'],
      ({ pluginId, expectedRevision }) => ({
        plugin_id: pluginId, expected_revision: expectedRevision, retain_tenant_data: true,
      }),
    ),
    'base.users.search': exactOutcome(operationTargets['base.users.search'], ({ query = '', limit = 10 }) => ({ query, limit })),
    'base.orgTeams.list': {
      capabilityId: operationTargets['base.orgTeams.list'], payload: () => ({}),
      legacy: value => value?.teams || [],
    },
    'base.teams.list': exactOutcome(operationTargets['base.teams.list'], () => ({})),
    'base.annotations.batch': {
      capabilityId: operationTargets['base.annotations.batch'],
      payload: ({ gids }) => ({ item_gids: gids }),
      legacy: value => Object.fromEntries((value?.items || []).map(item => {
        const { item_gid, ...summary } = item;
        return [item_gid, summary];
      })),
    },
    'base.annotations.get': exactOutcome(operationTargets['base.annotations.get'], ({ itemGid }) => ({ item_gid: itemGid })),
    'base.annotations.search': {
      capabilityId: operationTargets['base.annotations.search'],
      payload: ({ limit = 200, status = null, module = null }) => ({ limit, status, module }),
      legacy: value => value?.items || [],
    },
    'base.annotations.apply': annotationWrite(
      operationTargets['base.annotations.apply'],
      ({ itemGid, expectedRevision, status, schedule = null, note = '', attachments = [] }) => ({
        item_gid: itemGid, expected_revision: expectedRevision, status, schedule, note, attachments,
      }),
    ),
    'base.identity.session.profile.get': exactOutcome(operationTargets['base.identity.session.profile.get'], () => ({})),
    'base.users.list': exactOutcome(operationTargets['base.users.list'], () => ({})),
    'base.users.assignRole': {
      capabilityId: operationTargets['base.users.assignRole'],
      write: true,
      confirmation: 'user',
      payload: ({ userGid, newRole, externalSubtype = null }) => ({ user_gid: userGid, new_role: newRole, external_subtype: externalSubtype }),
      legacy: value => value,
    },
    'base.fileStore.publicConfig.get': exactOutcome(operationTargets['base.fileStore.publicConfig.get'], () => ({})),
    'base.savedViews.search': {
      capabilityId: operationTargets['base.savedViews.search'],
      payload: ({ module = '', listGid = null, limit = 200, offset = 0 }) => ({ module, list_gid: listGid, limit, offset }),
      legacy: value => value?.views || [],
    },
    'base.savedViews.create': savedViewWrite(
      operationTargets['base.savedViews.create'],
      ({ name, module = '', listGid = null, config, shareScope = 'private' }) => ({ name, module, list_gid: listGid, config, share_scope: shareScope }),
    ),
    'base.savedViews.update': savedViewWrite(
      operationTargets['base.savedViews.update'],
      ({ viewGid, expectedRevision, name, module, listGid, config, shareScope }) => ({
        view_gid: viewGid, expected_revision: expectedRevision, name, module, list_gid: listGid, config, share_scope: shareScope,
      }),
    ),
    'base.savedViews.copy': savedViewWrite(
      operationTargets['base.savedViews.copy'],
      ({ viewGid, name }) => ({ view_gid: viewGid, name }),
    ),
    'base.savedViews.delete': savedViewWrite(
      operationTargets['base.savedViews.delete'],
      ({ viewGid, expectedRevision }) => ({ view_gid: viewGid, expected_revision: expectedRevision }),
    ),
    'project.lists.search': { resolve: listSearch },
    'project.lists.patch': { resolve: listPatch },
    'project.lists.delete': { resolve: listDelete },
  };

  function exactOutcome(capabilityId, payload, write = false) {
    return {
      capabilityId, write, payload,
      legacy: value => value,
    };
  }

  function savedViewWrite(capabilityId, payload) {
    return { capabilityId, write: true, confirmation: 'user', payloadIdempotency: true, payload, legacy: value => value?.view };
  }

  function annotationWrite(capabilityId, payload) {
    return { capabilityId, write: true, confirmation: 'user', payloadIdempotency: true, payload, legacy: value => value?.annotation };
  }

  function pluginLifecycleWrite(capabilityId, payload) {
    return { capabilityId, write: true, confirmation: 'user', payloadIdempotency: true, payload, legacy: value => value?.installation };
  }

  function projectUpdate(capabilityId) {
    return {
      capabilityId,
      write: true,
      payload: ({ gid, updates }) => ({ arguments: { gid, updates } }),
      legacy: value => ({ success: true, data: value }),
    };
  }

  function defaultTransport(path, options) {
    const transport = rootTransport();
    if (typeof transport !== 'function') throw new TypeError('_cloudFetch 未就绪');
    return transport(path, options);
  }

  function rootTransport() {
    if (typeof window === 'undefined') return null;
    return window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
  }

  function defaultIdempotencyKey(capabilityId) {
    const nonce = globalThis.crypto?.randomUUID?.()
      || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${capabilityId}:${nonce}`;
  }

  function invocationError(response, capabilityId) {
    const envelope = response?.data;
    const detail = envelope?.error || response?.error || response?.detail || {};
    const error = new Error(detail.message || `能力调用失败：${capabilityId}@1`);
    error.code = detail.code || 'capability_invocation_failed';
    return error;
  }

  function invocationValue(response, capabilityId) {
    const envelope = response?.data;
    if (response?.success !== true || envelope?.ok !== true) {
      throw invocationError(response, capabilityId);
    }
    const value = envelope.data;
    return value?.data !== undefined && Object.keys(value).length === 1 ? value.data : value;
  }

  function confirmationCancelled(capabilityId) {
    const error = new Error(`已取消能力确认：${capabilityId}@1`);
    error.code = 'capability_confirmation_cancelled';
    return error;
  }

  function confirmationRequired(capabilityId) {
    const error = new Error(`需要明确确认才能调用：${capabilityId}@1`);
    error.code = 'capability_confirmation_required';
    return error;
  }

  function idempotencyKeyRequired(capabilityId) {
    const error = new Error(`需要稳定幂等键才能调用：${capabilityId}@1`);
    error.code = 'capability_idempotency_key_required';
    return error;
  }

  function createExistingCapabilityClient(_cloudFetch = defaultTransport, options = {}) {
    const idempotencyKeyFactory = options.idempotencyKeyFactory || defaultIdempotencyKey;

    async function request(capabilityId, action, body) {
      return _cloudFetch(`/api/v1/capabilities/${capabilityId}:${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }

    async function invoke(capabilityId, payload, invokeOptions = {}) {
      const requestBody = { version: 1, payload };
      if (invokeOptions.expectedResourceVersion !== undefined) {
        requestBody.expected_resource_version = String(invokeOptions.expectedResourceVersion);
      }
      if (invokeOptions.write) {
        requestBody.idempotency_key = invokeOptions.idempotencyKey
          || idempotencyKeyFactory(capabilityId, payload);
      }
      let response = await request(capabilityId, 'invoke', requestBody);
      if (response?.data?.error?.code === 'confirmation_required') {
        if (invokeOptions.confirmed !== true) throw invocationError(response, capabilityId);
        const confirmation = await request(capabilityId, 'confirm', requestBody);
        const token = confirmation?.success === true
          ? confirmation?.data?.confirmation_token
          : null;
        if (!token) throw invocationError(confirmation, capabilityId);
        response = await request(capabilityId, 'invoke', {
          ...requestBody,
          confirmation_token: token,
        });
      }
      return invocationValue(response, capabilityId);
    }

    async function call(name, args = {}, callOptions = {}) {
      const operation = operations[name];
      if (!operation) throw new TypeError(`不支持的现有能力迁移：${name}`);
      const resolved = operation.resolve ? operation.resolve(args) : operation;
      let payload = typeof resolved.payload === 'function' ? resolved.payload(args) : resolved.payload;
      if (resolved.idempotencyKeyRequired === true && !callOptions.idempotencyKey) {
        throw idempotencyKeyRequired(resolved.capabilityId);
      }
      const idempotencyKey = resolved.write === true
        ? (callOptions.idempotencyKey || idempotencyKeyFactory(resolved.capabilityId, payload))
        : undefined;
      if (resolved.payloadIdempotency === true) payload = { ...payload, idempotency_key: idempotencyKey };
      let confirmed = false;
      if (resolved.confirmation === 'user') {
        if (typeof callOptions.confirm !== 'function') throw confirmationRequired(resolved.capabilityId);
        confirmed = await callOptions.confirm({
          capabilityId: resolved.capabilityId,
          payload,
          idempotencyKey,
        }) === true;
        if (!confirmed) throw confirmationCancelled(resolved.capabilityId);
      }
      return resolved.legacy(await invoke(resolved.capabilityId, payload, {
        write: resolved.write === true, idempotencyKey, confirmed,
      }));
    }

    return { call, invoke };
  }

  return { createExistingCapabilityClient, operationTargets, resolveListCapability };
});
