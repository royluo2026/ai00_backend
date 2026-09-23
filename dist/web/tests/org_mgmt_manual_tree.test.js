'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const source = fs.readFileSync(path.join(__dirname, '..', 'org_mgmt', 'org_mgmt.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'org_mgmt', 'org_mgmt.html'), 'utf8')
  .replace(/<script[^>]+src=[^>]+><\/script>/g, '');

function response(data) {
  return { success: true, data: { ok: true, data: { data } } };
}

function boot({ responsibilityError = false, projectCount = 1, delayReads = false, withConfiguredLine = true } = {}) {
  let activeReads = 0;
  let maxActiveReads = 0;
  let detailReads = 0;
  let bopReads = 0;
  const projects = Array.from({ length: projectCount }, (_, index) => ({
    gid: `project-${index + 1}`, name: index === 0 ? '已有项目' : `项目 ${index + 1}`,
  }));
  const tracked = async value => {
    activeReads += 1;
    maxActiveReads = Math.max(maxActiveReads, activeReads);
    if (delayReads) await new Promise(resolve => setTimeout(resolve, 5));
    activeReads -= 1;
    return value;
  };
  const dom = new JSDOM(html, { runScripts: 'dangerously', url: 'http://localhost/' });
  const { window } = dom;
  window.AI00Business = {
    available: () => true,
    invoke: async id => {
      assert.equal(id, 'base.feishu.organization_user.search');
      return { data: [{ db_gid: 'user-2', name: '李四', email: 'lisi@example.com' }] };
    },
    request: async (id, envelope) => {
      if (id === 'project.project.read.atomic.projects_search') {
        return response(projects);
      }
      if (id === 'project.org_management.read') {
        if (responsibilityError) return { success: false, error: { message: '责任树服务不可用' } };
        return response({ items: [{
          gid: 'project-1', name: '已有项目', revision: 0,
          lines: withConfiguredLine
            ? [{ gid: 'line-1', name: '总装线', leader_user_gids: [], bop_line_gid: null }]
            : [],
        }], next_cursor: null });
      }
      if (id === 'base.project_manager.read') {
        detailReads += 1;
        return tracked(response({ project_gid: envelope.payload.project_gid, revision: 0, managed: false, managers: [] }));
      }
      if (id === 'craft.bop.active_line.search') {
        detailReads += 1;
        bopReads += 1;
        return tracked(response({ items: [], next_cursor: null }));
      }
      if (id === 'project.member.read') {
        detailReads += 1;
        assert.equal(envelope.payload.operation, 'members.list',
          'project.member.read 的 operation 必须位于能力 payload 顶层');
        assert.match(envelope.payload.arguments.project_gid, /^project-\d+$/);
        assert.deepEqual(Object.keys(envelope.payload.arguments), ['project_gid']);
        return tracked(response({
          success: true,
          data: [{ gid: 'membership-1', project_gid: envelope.payload.arguments.project_gid, user_gid: 'user-1', name: '张三', role: 'member' }],
        }));
      }
      throw new Error(`unexpected capability: ${id}`);
    },
  };
  window.eval(`${source}\nwindow.__loadProjects = loadProjects; window.__loadMatrix = _loadMatrix; window.__toggleResponsibilityProject = _toggleResponsibilityProject;`);
  dom.loadStats = () => ({ maxActiveReads, detailReads, bopReads });
  return dom;
}

{
  const dom = new JSDOM(html);
  const { document } = dom.window;
  assert.equal(document.querySelector('#pm-view-config select'), null,
    '项目责任树不能显示项目下拉框');
  assert.ok(document.querySelector('#pm-view-matrix #matrix-project-filter'),
    '项目筛选只属于总览矩阵');
  dom.window.close();
}

(async () => {
  const success = boot();
  await success.window.__loadProjects();
  assert.equal(success.window.document.querySelector('.pm-project-node strong')?.textContent, '已有项目',
    '已有项目必须在责任树中显示，即使尚未配置责任人');
  assert.equal(success.loadStats().detailReads, 0,
    '首屏只能加载项目摘要，不得预读每个项目的经理、成员和 BOP 详情');
  assert.equal(success.window.document.querySelector('[data-add-manager="project-1"]'), null,
    '折叠项目不应渲染详情操作');
  await success.window.__toggleResponsibilityProject('project-1');
  assert.ok(success.window.document.querySelector('[data-add-manager="project-1"]'),
    '项目节点必须提供添加项目经理入口');
  assert.ok(success.window.document.querySelector('[data-add-member="project-1"]'),
    '项目节点必须提供添加普通成员入口');
  assert.ok(success.window.document.querySelector('[data-add-line-leader="line-1"]'),
    '线体节点必须提供添加负责人的入口');
  assert.ok(success.window.document.getElementById('modal-project-person'),
    '项目人员使用独立的飞书搜索选择器');
  success.window.document.querySelector('[data-add-manager="project-1"]').click();
  const search = success.window.document.getElementById('search-project-person-input');
  search.value = '李四';
  search.dispatchEvent(new success.window.Event('input', { bubbles: true }));
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.match(success.window.document.getElementById('search-project-person-results').textContent, /李四/,
    '添加人员必须调用飞书搜索并显示结果');
  await success.window.__loadMatrix();
  assert.match(success.window.document.getElementById('pm-matrix-wrap').textContent, /张三/,
    '普通项目成员必须进入总览矩阵');
  success.window.close();

  const bounded = boot({ projectCount: 6, delayReads: true, withConfiguredLine: false });
  await bounded.window.__loadProjects();
  assert.equal(bounded.loadStats().detailReads, 0,
    '多个项目的首屏加载不得随项目数放大详情请求');
  assert.equal(bounded.window.document.querySelectorAll('.pm-project-node').length, 6,
    '首屏仍须完整显示项目摘要');
  await bounded.window.__toggleResponsibilityProject('project-1');
  assert.ok(bounded.loadStats().maxActiveReads <= 3,
    '展开单个项目最多并发读取该项目的三类详情');
  assert.equal(bounded.loadStats().detailReads, 2,
    '无人工线体的项目只读取经理和成员');
  assert.equal(bounded.loadStats().bopReads, 0,
    '没有人工线体时不得预加载 BOP 映射选项');
  bounded.window.close();

  const failed = boot({ responsibilityError: true });
  await failed.window.__loadProjects();
  assert.match(failed.window.document.getElementById('pm-config-body').textContent, /加载失败/,
    '责任配置加载失败不能伪装成暂无项目');
  assert.ok(failed.window.document.querySelector('[data-retry-projects]'));
  failed.window.close();

  console.log('org management manual tree behavior passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
