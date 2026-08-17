import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const exampleUrl = new URL('../examples/bop-line-compare/', import.meta.url);
const runtimeUrl = new URL('bop-runtime.js', exampleUrl);
const candidateViewUrl = new URL('candidate-view.js', exampleUrl);
const manifestUrl = new URL('plugin.json', exampleUrl);
const runtime = fs.existsSync(fileURLToPath(runtimeUrl)) ? await import(runtimeUrl) : {};
const candidateView = fs.existsSync(fileURLToPath(candidateViewUrl)) ? await import(candidateViewUrl) : {};
const manifest = fs.existsSync(fileURLToPath(manifestUrl))
  ? JSON.parse(fs.readFileSync(fileURLToPath(manifestUrl), 'utf8'))
  : {};

const capabilityIds = [
  'base.project.search',
  'craft.bop.version.list',
  'craft.bop.execution_structure.get',
  'craft.bop.work_package.get',
  'craft.bop.linked_parts.get',
];

function completed(data) {
  return { ok: true, status: 'completed', data };
}

function fixtureClient({ failWorkPackage = false } = {}) {
  return {
    calls: [],
    async invoke(id, payload) {
      this.calls.push({ id, payload });
      if (id === 'base.project.search') return completed({ query: payload.query, total: 1, items: [{ object_ref: 'project:p1', title: 'Atlas X1', owner: 'project_management' }] });
      if (id === 'craft.bop.version.list') return completed({ items: [{ version_gid: 'bop-1', version_tag: 'V1', bop_name: '总装 BOP', family_gid: null, project_gid: payload.project_gid, status: 'baseline', lifecycle_phase: 'published', revision: 4, updated_at: '2026-08-17T00:00:00Z', archived: false }], next_cursor: null });
      if (id === 'craft.bop.execution_structure.get') return completed({
        contract_id: 'craft.execution_structure', contract_version: 1, official: true,
        source: { bop_version_gid: payload.version_gid, project_gid: 'p1', revision: 4 },
        published_at: '2026-08-17T00:00:00Z', content_hash: 'sha256:demo', dependencies: [], conditions: [],
        nodes: [{ node_id: 'line-1', parent_id: null, kind: 'line_process', sequence: 10, name: '底盘一线', vpps: null, part_refs: [], tool_refs: [], fixture_refs: [], equipment_refs: [], knowledge_refs: [], rule_refs: [] }],
        operations: [],
      });
      if (id === 'craft.bop.work_package.get') {
        if (failWorkPackage) return { ok: false, status: 'failed', error: { code: 'permission_denied', message: 'Denied', retryable: false, details: { token: 'DO_NOT_LEAK' } } };
        return completed({
          version_gid: payload.version_gid, revision: 4, scope: payload.scope,
          work_items: [{ operation_id: 'op-1', sequence: 10, kind: 'operation', name: '拧紧后副车架', predecessor_ids: [], resource_refs: ['tool:wrench'], model_refs: [], part_refs: ['part:bolt'], knowledge_refs: [], rule_refs: [], parameters: { parent_node_id: 'station-1', vpps: 'TA-340' } }],
          parts: ['part:bolt'], tools: ['tool:wrench'], fixtures: [], equipment_requirements: [], knowledge_refs: [], rule_refs: [],
        });
      }
      if (id === 'craft.bop.linked_parts.get') return completed({ version_gid: payload.version_gid, revision: 4, items: [{ part_gid: 'bolt', part_no: 'B-14', name: '法兰螺栓', usage: [{ entry_gid: 'op-1', entry_title: '拧紧后副车架' }] }] });
      throw new Error(`Unexpected capability ${id}`);
    },
  };
}

test('manifest declares exactly the five mounted read capabilities with major 1', () => {
  assert.equal(manifest.plugin_id, 'devteam.ai00.bop-line-compare');
  assert.equal(manifest.version, '1.0.0');
  assert.equal(manifest.runtimes?.web?.sandbox, 'allow-scripts');
  assert.deepEqual(manifest.permissions, capabilityIds);
  assert.deepEqual(manifest.capabilities?.required, capabilityIds.map(id => ({ id, major: 1 })));
  assert.deepEqual(manifest.capabilities?.optional, []);
});

test('runtime discovers a project, BOP, line, and bounded line context through declared capabilities', async () => {
  assert.equal(typeof runtime.createTrace, 'function');
  const client = fixtureClient();
  const trace = runtime.createTrace();
  const projects = await runtime.searchProjects(client, 'Atlas', trace);
  const bops = await runtime.loadBopChoices(client, projects[0].object_ref, trace);
  const structure = await runtime.loadBopStructure(client, bops[0].version_gid, trace);
  const context = await runtime.loadLineContext(client, bops[0].version_gid, structure.lines[0].node_id, trace);

  assert.equal(context.operations[0].parameters.vpps, 'TA-340');
  assert.equal(context.linkedParts[0].name, '法兰螺栓');
  assert.deepEqual(client.calls.map(call => call.id), capabilityIds);
  assert.ok(client.calls.every(call => capabilityIds.includes(call.id)));
  assert.deepEqual(trace.items.map(item => item.status), ['completed', 'completed', 'completed', 'completed', 'completed']);
});

test('buildComparison keeps process, part, and tool material non-empty', () => {
  const context = {
    operations: [{ operation_id: 'op-1', name: '拧紧后副车架', resource_refs: ['tool:wrench'], part_refs: ['part:bolt'], parameters: { vpps: 'TA-340' } }],
    linkedParts: [{ part_gid: 'bolt', part_no: 'B-14', name: '法兰螺栓', usage: [{ entry_gid: 'op-1' }] }],
  };
  const model = runtime.buildComparison(context, structuredClone(context));

  assert.equal(model.alignment.exact.length, 1);
  assert.equal(model.parts.common[0].part_no, 'B-14');
  assert.deepEqual(model.tools.common, ['tool:wrench']);
});

test('failed capability exposes a typed public error and trace omits raw details', async () => {
  const client = fixtureClient({ failWorkPackage: true });
  const trace = runtime.createTrace();

  await assert.rejects(
    runtime.loadLineContext(client, 'bop-1', 'line-1', trace),
    error => error.code === 'permission_denied' && error.message === 'Denied',
  );

  assert.equal(trace.items.at(-1).status, 'failed');
  assert.equal(trace.items.at(-1).error_code, 'permission_denied');
  const serialized = JSON.stringify(trace.items);
  assert.doesNotMatch(serialized, /DO_NOT_LEAK|token|details/i);
});

test('plugin page exposes the complete two-column comparison workflow', () => {
  const htmlPath = fileURLToPath(new URL('index.html', exampleUrl));
  const html = fs.existsSync(htmlPath) ? fs.readFileSync(htmlPath, 'utf8') : '';
  for (const id of [
    'left-project-query', 'right-project-query', 'left-bop', 'right-bop',
    'left-line', 'right-line', 'operation-query', 'auto-align', 'vpps-only',
    'left-candidate-project', 'right-candidate-project',
    'left-candidates', 'right-candidates', 'aligned-candidate-pairs', 'process-view', 'parts-view',
    'tools-view', 'trace-list',
  ]) {
    assert.match(html, new RegExp(`id=["']${id}["']`), `missing UI region ${id}`);
  }
});

test('aligned candidates use paired cards with the same row box on both sides', () => {
  assert.equal(typeof candidateView.renderAlignedCandidateRows, 'function');
  const html = candidateView.renderAlignedCandidateRows([{
    left: { operation_id: 'left-1', name: '左侧操作', parameters: { vpps: 'VPPS-1' } },
    right: { operation_id: 'right-1', name: '右侧操作', parameters: { vpps: 'VPPS-1' } },
    method: 'vpps', score: 1, reasons: ['VPPS 一致'],
  }], value => String(value));

  assert.match(html, /^<div class="candidate-pair" data-index="0">/);
  assert.equal((html.match(/class="candidate/g) || []).length, 3);
  assert.match(html, /data-side="left"/);
  assert.match(html, /data-side="right"/);
});

test('candidate project marker identifies the selected project by name and reference', () => {
  assert.equal(typeof candidateView.formatProjectIdentity, 'function');
  assert.equal(
    candidateView.formatProjectIdentity({ title: 'Atlas X1', object_ref: 'project:atlas-x1' }),
    'Atlas X1 · project:atlas-x1',
  );
});

test('plugin controller stays inside the SDK Mount and sandbox boundary', () => {
  const appPath = fileURLToPath(new URL('app.js', exampleUrl));
  const app = fs.existsSync(appPath) ? fs.readFileSync(appPath, 'utf8') : '';
  assert.match(app, /Ai00PluginClient/);
  assert.doesNotMatch(app, /\bfetch\s*\(|XMLHttpRequest|document\.cookie|contentDocument|parent\.document|randomUUID/);
});
