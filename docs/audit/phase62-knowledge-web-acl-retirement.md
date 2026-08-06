# Phase 62 — Knowledge Web ACL 死入口退役

日期：2026-08-06
后端分支：`codex/capability-wave-a`
Web 分支：`codex/knowledge-open-collaboration-web`
Web 本地提交：`a71a401`

## 1. 背景

Phase 60 已让同 tenant 认证成员通过正常 Knowledge Capability 看、改文档，并停止正常路径的 ACL SQL 读写。外部 Web 页面仍显示“访问权限”，调用三个未注册 ACL Capability，造成必然失败的死入口和“存在文档私有权限”的错误暗示。

## 2. Web 改动

在独立 Web worktree 中完成：

- 移除文档工具栏“访问权限”按钮和点击监听。
- 删除 `_showWorkspaceAcl` 及其 list/grant/revoke 调用。
- 删除只服务该弹窗的 ACL CSS。
- 新增 `scripts/test_knowledge_open_collaboration.js`，禁止 ACL 按钮、函数、Capability ID 和团队成员权限请求重新进入 Knowledge 页面。
- 将新契约接入 `test`、`test:all` 和 `test:integration` 三条守卫链。

系统级权限申请功能不在本项范围内，没有删除。

## 3. TDD 与验证

- 基线：Web `123/123`，其余静态守卫全部通过。
- RED：新契约首先因 `access.textContent = '访问权限'` 明确失败。
- GREEN：ACL UI/调用删除后新契约通过。
- 完整 Web 回归：`123/123`，web-only defaults/docs/entrypoints/fixture paths/runtime backend resolution 和 Knowledge 新契约全部通过。
- `node --check web/knowledge_hub/knowledge_hub.js`：通过。
- `git diff --check`（CRLF 文件按 `cr-at-eol`）：通过。

## 4. 测试归属修正

后端仓库原有 `test_knowledge_workspace_web.py` 反向断言 ACL UI 和三个旧 Capability 必须存在。该断言与批准的开放协作契约冲突，也跨仓库读取 `deploy` 工作目录。现删除这一过时方法；ACL 不得回归的契约由 Web 仓库自己的默认测试链负责。

后端仍保留其他跨仓库 Knowledge UI 断言，后续宜逐步迁回 Web 仓库，但本阶段不扩大范围。

## 5. 集成状态

- 原 Web `deploy` 分支未修改。
- Web 改动仅提交到本地功能分支，未 push、未部署。
- `KNOW-003` 标记为“实施中”，因为 ACL helper、历史数据与旧表是否迁移/删除仍需真实数据盘点；本阶段没有做破坏性 DDL。
- 后端 Capability 分支仅记录审计和移除过时测试，不把 Web 本地提交伪装成已部署状态。
