# Phase 61 — Tasks 6–14 完成度审计

日期：2026-08-06
分支：`codex/capability-wave-a`
审计结论：`部分完成，不能宣称整批完成或可生产发布`

## 1. 逐任务结论

| Task | 结论 | 已取得证据 | 尚缺条件 |
| --- | --- | --- | --- |
| 6 Knowledge | 代码与离线自动化完成 | 受治理文档/上下文能力、固定 revision、证据、OIS Hash、租户内开放协作与不可变归因；Phase 60 | 真实 OIS/OceanBase 烟测；旧 Web ACL 死入口退役（`KNOW-003`） |
| 7 Ontology 存储 | 代码与离线自动化完成 | OceanBase 兼容迁移、不可变 release/proposal/review/active-ref、canonical Hash；Phase 51 | 真实迁移与 OIS 快照验收 |
| 8 Ontology 概念 | 代码与离线自动化完成 | 固定 release 的 resolve/get、歧义诚实返回、mapping assess 不冒充语义真相；Phase 52 | 真实本体数据验收 |
| 9 Ontology 提案 | 代码与离线自动化完成 | 类型化变更、不可变 revision、Agent 不得批准、作者不能独自批准；Phase 53 | 业务评审角色和真实流程验收 |
| 10 Ontology 发布 | 代码与离线自动化完成 | publish/activate 分离、语义 diff、预期 active ref 和迁移门槛；Phase 54 | 真实迁移、Gateway 管理确认和回滚演练 |
| 11 System/Semantic/Base | 代码与离线自动化完成 | 稳定 refs/evidence、无任意查询语言、搜索/活动/作业/身份/血缘/影响/语义/项目能力；Phase 55 | 真实领域 provider 联调和权限矩阵验收 |
| 12 Craft Policy gate | 框架完成，业务治理未完成 | 不可变 Policy 模型、完整性门槛、四项 VPPS 阻塞盘点；Phase 56 | `CRAFT-002` 四项规则全部业务输入与证据 |
| 13 Craft 写能力 | 未启动，符合计划 | 三项权威 Capability 保持未注册，未绕过硬门槛 | 完成并签署 `CRAFT_VALIDATION_POLICY_INPUT_TEMPLATE.md` |
| 14 消费者迁移 | 代码与自动化契约完成 | Web 首条 BOP 读链、Agent、REST、Agent Runtime、MCP 共用 Catalog/Result/evidence；Phase 57 | 真实 JWT/OceanBase/OIS 端到端烟测；继续治理未迁移旧消费者 |

## 2. Task 13 硬门槛

当前四项阻塞检查不变：

- `vpps.master_data`
- `vpps.parent`
- `vpps.hierarchy_prefix`
- `vpps.fastener_main_part`

每项都缺少业务批准的 `source_ref`、唯一 Owner、scope、severity、mechanism、threshold、algorithm_ref、check/Policy 版本和 evidence schema；`publish_check` 还缺正例、反例、边界例和历史回放证据。因此不能实现或注册：

- `craft.bop.version.validate`
- `craft.bop.version.publish`
- `craft.pbom.vpps.validate`

可填写治理入口：`docs/governance/CRAFT_VALIDATION_POLICY_INPUT_TEMPLATE.md`。

## 3. 自动化验证证据

成功证据：

- Phase 60 最终代码的完整后端离线回归：`579 passed in 13.57s`，0 warning。
- 本轮 Tasks 6–12 + Task 14 相关聚合回归：`153 passed in 5.23s`；唯一 warning 为 pytest 缓存目录权限。
- Task 14 Agent Runtime：`3 passed`。
- Task 14 MCP Gateway：`2 passed`。
- 外部 TypeScript 源码与测试文件 Hash 复核仍与 Phase 57 相同。

本轮还尝试再次运行完整后端套件。产品断言中 `567 passed`，但 12 项依赖 `tmp_path` 的测试在 fixture setup 阶段因当前 Windows 沙箱拒绝 pytest 创建/读取 `0700` 临时根目录而未执行；这不是新的产品断言失败，也不能替代 Phase 60 已取得的完整成功证据。

## 4. OceanBase 与部署边界

离线测试已覆盖 OceanBase MySQL 禁用语法、版本化 migration、无独立 schema 前提和 mock 合同，但以下生产级证据尚不存在：

1. 在授权的 OceanBase 测试租户执行 migration preflight 和实际迁移。
2. 使用真实 OIS 验证 Knowledge/Ontology 不可变快照与 Hash。
3. 使用真实 JWT 验证 Web、Agent、Public REST 和 MCP 的身份、Catalog 过滤和审计一致性。
4. 验证 migration 重放、失败恢复和旧路由退役条件。

本阶段没有连接数据库、push、部署或修改远端。

## 5. 边界与遗留风险

- Knowledge 的正常 Capability 路径已停止 ACL 读写；ACL 表和 helper 只作未注册兼容保留，待真实数据盘点后再决定迁移/删除。
- 外部 Web `knowledge_hub.js` 仍有三个未注册 ACL 调用和权限 UI；必须在独立 Web 功能分支处理，不能直接改 `deploy` 分支。
- Task 14 只证明首批受治理消费路径，不代表所有旧 API 已 Capability 化，也不代表应把所有内部功能暴露为 Capability。
- 插件仍只能调用 Catalog 明确标记 `plugin_callable` 的能力；插件不能注册官方领域权威能力或绕过 Task 13 Policy gate。

## 6. 下一步顺序

1. 由业务 Owner 填写、评审并签署 Craft Policy 输入模板。
2. 输入获批后按 TDD 实施 Task 13 的 validate/create/publish/archive/preview/apply/import-preview/VPPS 能力。
3. 在独立 Web 分支完成 `KNOW-003`，移除 ACL 死入口并同步构建产物。
4. 获得测试环境授权后执行 OceanBase/OIS/JWT 端到端烟测；通过前不宣称生产就绪。
