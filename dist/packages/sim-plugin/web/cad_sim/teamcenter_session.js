(function (global) {
  'use strict';
  const clean = value => String(value || '').trim();
  function common(query, revisionId, revisionRule, configurationDate) {
    if (!query || query.length > 128 || !revisionRule || revisionRule.length > 128)
      throw new Error('teamcenter_search_input_invalid');
    return { endpoint_id: 'tc-production', query, revision_id: revisionId,
      revision_rule: revisionRule, configuration_date: configurationDate, limit: 20 };
  }
  function projectSearchInput(projectNumber, revisionRule, configurationDate) {
    const value = clean(projectNumber);
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,111}$/.test(value) || /-ENG\d+$/i.test(value))
      throw new Error('teamcenter_project_number_only');
    return common(`${value}-ENG00001`, '00', clean(revisionRule), clean(configurationDate));
  }
  function fuzzySearchInput(query, revisionId, revisionRule, configurationDate) {
    return common(clean(query), clean(revisionId), clean(revisionRule), clean(configurationDate));
  }
  const isReady = value => value?.state === 'ready' && typeof value.masked_username === 'string';
  global.AI00TeamcenterSession = Object.freeze({ fuzzySearchInput, isReady, projectSearchInput });
})(typeof window !== 'undefined' ? window : globalThis);
