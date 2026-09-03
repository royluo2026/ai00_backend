(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.KnowledgeResourceModel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const RESOURCE_TABS = Object.freeze([
    { value: 'socket', label: '套筒' },
    { value: 'tool', label: '工具' },
    { value: 'fixture', label: '工装' },
    { value: 'equipment', label: '设备' },
  ]);

  const canManageResources = role => role === 'knowledge_admin' || role === 'super_admin';
  const canReviewStaging = role => canManageResources(role) || role === 'project_admin';
  const resourceTypeForSection = section => ({
    vpps_sockets: 'socket', vpps_tools: 'tool',
    vpps_fixtures: 'fixture', vpps_equipments: 'equipment',
  })[section] || null;
  const resourcePatchBody = (row, draft) => ({
    expected_resource_version: row.resource_version,
    code: draft.code,
    name: draft.name,
    attributes: draft.attributes,
  });
  const resourceRetireBody = row => ({ expected_resource_version: row.resource_version });

  return {
    RESOURCE_TABS, canManageResources, canReviewStaging, resourceTypeForSection,
    resourcePatchBody, resourceRetireBody,
  };
});
