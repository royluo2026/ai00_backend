# Phase 57 — 首批受治理 Capability 消费者

日期：2026-08-06
分支：`codex/capability-wave-a`

## 已实现

- Catalog 在服务端按当前用户权限过滤；Agent/API/MCP隐藏deprecated别名；插件仅看到显式`plugin_callable`能力。
- 首批新增Knowledge、Ontology、System和Craft能力全部保持`plugin_callable=false`；没有借本轮迁移扩大第三方插件权限。
- Web BOP页面三个版本列表读取点统一迁移到`craft.bop.version.list` v1。
- Agent `search_knowledge`迁移到有界`knowledge.context.retrieve`，最多10条并保留固定revision引用和evidence。
- Agent BOP结构查询迁移到`craft.bop.execution_structure.get`；Agent处理器不再使用entries内部路由完成该场景。
- Agent本体解释先调用`ontology.concept.resolve`处理歧义，再按固定release调用`ontology.concept.get` schema视图。
- Agent Runtime与MCP Gateway均从服务端过滤Catalog选择能力，并保留完整`CapabilityResult`、稳定错误详情、evidence和audit。
- 增加批准Capability静态快照、禁止内部协议清单、REST消费者E2E和Agent适配器行为测试。
- 修复四个测试夹具对普通目录拓扑的硬编码，使其同时支持Git worktree。

详细调用映射见`docs/audit/agreed-capability-consumer-matrix.md`。

## 验证证据

- Task 14聚焦验收：`33 passed, 1 warning`。
- Tasks 6–12与Task 14联合回归：`107 passed, 1 warning`。
- Agent/REST/引用适配器子集：`10 passed, 1 warning`。
- worktree路径夹具：`10 passed`。
- Agent Runtime：`3 passed, 0 failed`，包含Catalog过滤URL与CapabilityResult/evidence契约。
- MCP Gateway：`2 passed, 0 failed`，包含Catalog过滤URL与CapabilityResult/error/evidence契约。
- `node --check dist/packages/craft-plugin/web/bop/bop.js`：通过。
- `git diff --check`：在阶段性检查时通过；提交前再次执行。

完整后端套件使用只指向`127.0.0.1:9`的离线配置执行，结果为`519 passed, 53 failed, 3 warnings`。53项失败集中在既有数据库/路由mock模型、旧Schema前缀断言、VPPS旧前端外部文件断言、运行时保存配置假设和少量遗留领域测试。它们不在本轮聚焦门内，因此本Phase不能宣称“完整后端套件通过”或“生产验收完成”。

## 数据库安全事件记录

第一次运行完整套件时，测试进程继承了桌面保存的数据库配置；启动日志显示连接池成功连接到已配置的OceanBase测试地址。没有执行Migration、部署、显式写命令或业务操作，但建立真实连接本身超出了本轮预期。发现后没有用同一配置重跑；后续完整套件改用仅指向`127.0.0.1:9`的离线配置。后续应让pytest默认禁用桌面保存配置，真实数据库测试只能通过显式opt-in标记执行。

## 尚未完成与硬门槛

- Task 13未启动：四项VPPS检查仍缺少业务Owner批准的source、Owner、threshold、algorithm、Policy版本和正/反/边界/历史回放证据。
- 真实OceanBase/OIS/JWT部署烟测未执行；旧路由仍保留，不能标记退役。
- `AGENT-001`仍为实施中：本轮只迁移三个Agent读取场景，其他内部REST和失效工具声明仍需逐项治理。
- Knowledge团队协作政策已确定为同tenant成员可看可改并保留不可变归因，但现有文档级SQL ACL执行仍未移除；该访问扩展需要用户在安全提示后显式确认。
- 没有push、部署或远端变更。

## 根级/外部路径SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `services/agent-runtime/src/capability-client.ts` | `BD638E46C1CC841FF014738CED4AC21FBDD8BE75983C8BDC147E9B0A11D347F7` |
| `services/agent-runtime/test/runtime-policy.test.ts` | `120F5A89D9AAC793C604D17A7DBB88C25BFB2EA2412B91F1BF77824E281E5A66` |
| `services/mcp-gateway/src/capability-client.ts` | `DDD966A14B1D2CC4D24CC14E6A612497084D17EFC8352B373D5427ECFCE2D91D` |
| `services/mcp-gateway/test/schema.test.ts` | `4F0C0E18FECF2EBDA959A05DAFD931C9B370503B5E2A58D0091E093F6DDB7341` |
| `API_CAPABILITY_AUDIT.md` | `0B7E2B7DD1CEBE56F188283DF598BFB71B0BD15DFC5527B74803B851BD73C77F` |
| `SYSTEM_OPTIMIZATION_BACKLOG.md`（提交前内容） | `A2E0908B46A327217CDF16DE8C1496CA2EADCABCE8833A6965BB65756FF1BDDD` |

`SYSTEM_OPTIMIZATION_BACKLOG.md`位于当前Git仓库中，最终提交会记录其Git对象；上表Hash用于根级阶段日志对账。
