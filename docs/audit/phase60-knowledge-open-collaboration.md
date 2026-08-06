# Phase 60 — Knowledge tenant 开放协作契约收口

日期：2026-08-06
分支：`codex/capability-wave-a`

## 完成度审计发现

Task 6 的 Capability Spec 已经是空权限要求，ACL Capability 也没有注册，但正常 Knowledge 文档 SQL 仍通过 `workmanship_know_document_acl` 判断读写权限，创建文档还会写入用户/team ACL。空间检索和建文档也仍把 `private/team` 当作访问边界。这与已批准的“同 tenant 认证成员均可看、均可改；空间不作 ACL 边界；修改必须留不可变归因”不一致。

## 本阶段改动

- `knowledge.document.revise`：只按 `document_gid + tenant_gid` 锁定文档，不再拼接文档 ACL。
- `knowledge.document.get/search/history.get/diff/restore` 的正常读取链路：只保留 tenant 和固定 revision 约束。
- `knowledge.document.create`：不再写用户管理员/team 编辑 ACL。
- `knowledge.space.search`：返回当前 tenant 的全部空间；历史 `visibility` 仅作展示元数据，新建空间/文档只能声明 `team`，避免制造假私有语义。
- 在任一当前 tenant 空间中创建文档不再依赖空间创建者或可见性。
- 乐观并发 `base_revision_gid`、OIS 内容 Hash、写入确认、revision 创建者/channel/delegated user/Agent/plugin/request/before-after Hash/change summary 均保持不变。
- ACL 表、迁移历史和未注册兼容 helper 暂时保留，避免无数据迁移证据时做破坏性删除。

## TDD 与验证

- RED：新测试准确捕获正常 Capability 中的 `workmanship_know_document_acl` 和空间可见性过滤，`2 failed`，随后空间门槛测试 `1 failed, 2 passed`。
- GREEN：Knowledge 开放协作、文档、上下文和契约聚焦测试 `17 passed`。
- Task 6 当前真实文件聚焦验收（含 revision store、migration、OceanBase）：`33 passed`。
- 完整后端离线回归：`579 passed in 13.57s`，0 warning。
- 没有连接真实数据库、push 或部署。

## 明确保留的遗留项

外部 `workmanship-web/web/knowledge_hub/knowledge_hub.js` 仍展示“访问权限”并调用三个未注册 ACL Capability。它不是本轮受治理 Capability 后端路径，但属于死入口，必须在独立 Web 功能分支移除后再同步构建产物。当前不会直接修改或提交 `deploy` 分支。

旧 ACL 数据和表是否最终迁移/删除，必须先做真实数据盘点；本阶段只停止新增依赖，不做物理删除。
