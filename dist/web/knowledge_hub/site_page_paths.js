const KNOWLEDGE_SITE_PAGE_PACKAGES = Object.freeze({
  task: 'craft-plugin', issue: 'craft-plugin', project: 'craft-plugin',
  bop: 'craft-plugin', ebom: 'craft-plugin', std_op_lib: 'craft-plugin',
  craft_element_lib: 'craft-plugin', factory_resource: 'craft-plugin',
  craft_table: 'craft-plugin', lineage_view: 'craft-plugin', gbop: 'craft-plugin',
  gbop_lineage: 'craft-plugin', approval: 'craft-plugin', data_hub: 'craft-plugin',
  template_hub: 'craft-plugin', craft_hub: 'craft-plugin', project_hub: 'craft-plugin',
  auto_canvas: 'craft-plugin', flow_canvas: 'agent-plugin',
  automation_hub: 'agent-plugin', cad_sim: 'sim-plugin',
});

function resolveKnowledgeSitePageUrl(path) {
  const value = String(path || '');
  if (!value || value.startsWith('/')) return value || 'about:blank';
  const plugin = KNOWLEDGE_SITE_PAGE_PACKAGES[value.split('/', 1)[0]];
  return plugin ? `/packages/${plugin}/web/${value}` : `../${value}`;
}

if (typeof window !== 'undefined') window.resolveKnowledgeSitePageUrl = resolveKnowledgeSitePageUrl;
if (typeof module !== 'undefined') module.exports = { resolveKnowledgeSitePageUrl };
