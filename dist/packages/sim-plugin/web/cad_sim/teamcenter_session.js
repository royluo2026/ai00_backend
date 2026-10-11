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
  function createSessionState({api,onChange}) {
    let sequence=0,disposed=false;
    async function run(method,input) {
      if(disposed)return null;
      const current=++sequence;onChange(method==='teamcenterLogin'?'signing-in':'checking');
      try {
        if(typeof api?.[method]!=='function')throw Error('teamcenter_login_unavailable');
        const status=await api[method](input);
        if(!disposed&&sequence===current)onChange(isReady(status)?'ready':'signed-out',status);
        return status;
      } catch(error) {
        if(!disposed&&sequence===current)onChange('error',null,error?.message||'Teamcenter 状态检查失败');
        throw error;
      }
    }
    const refresh=()=>run('teamcenterGetSession');
    const off=api?.onTeamcenterSessionChanged?.(()=>refresh().catch(()=>null));
    return {refresh,login:input=>run('teamcenterLogin',input),logout:()=>run('teamcenterLogout'),
      dispose(){disposed=true;++sequence;off?.();}};
  }
  global.AI00TeamcenterSession = Object.freeze({ fuzzySearchInput, isReady, projectSearchInput, createSessionState });
})(typeof window !== 'undefined' ? window : globalThis);
