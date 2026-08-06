# 已确认 Capability 首批消费者迁移矩阵

日期：2026-08-06
分支：`codex/capability-wave-a`
范围：Task 14 的四个真实场景；只记录已落地路径，不把兼容路由存在误报为已退役。

## 迁移矩阵

| 场景 | 旧调用 | 新 Capability | 消费者 | 版本 | 发布开关 | 旧调用观测 | 当前状态 |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| Web 查询 BOP 版本列表 | `GET /api/bop/versions` | `craft.bop.version.list` | `dist/packages/craft-plugin/web/bop/bop.js` | 1 | 无；同一页面内直接切换 | 该页面三个版本列表读取点已清零；旧路由仍保留给其他未迁移页面/内部流程 | 代码迁移完成，待真实部署烟测 |
| Agent 查询 BOP 正式执行结构 | `GET /api/bop/versions/{version_gid}/entries` | `craft.bop.execution_structure.get` | `get_bop_entries`、`list_asm_lines` | 1 | 无；Agent Tool 适配器直接切换 | Agent 处理器中该旧路径已清零；其他编辑型页面读取不在本场景范围 | 代码迁移完成，待真实数据烟测 |
| Agent 检索决策知识上下文 | `GET /api/knowledge_hub/items`、旧 `knowledge.search` 适配 | `knowledge.context.retrieve` | `search_knowledge`、系统提示知识注入 | 1 | 无；限制 `limit <= 10` | `search_knowledge` 已无旧搜索回退；Agent 的 `global_search` 仍有独立兼容知识搜索，登记在 AGENT-001 | 代码迁移完成，引用证据测试通过 |
| Agent 解释本体概念 | `GET /api/ontology/schema/{node_type}` | `ontology.concept.resolve` → `ontology.concept.get` | `get_ontology_schema` | 1 | 无；先消歧再固定 release 读取 schema | Agent 处理器中旧 ontology schema 路径已清零；底层管理 API 未退役 | 代码迁移完成，待真实本体 release 烟测 |

## 公共入口契约

- Web、Agent Runtime、Public REST 与 MCP 都使用 `/api/v1/capabilities/{id}:invoke` 的版本化调用协议。
- Agent Runtime Catalog 使用 `consumer=agent`；MCP 使用 `execution=cloud&consumer=mcp`。Catalog 在服务端按当前用户权限过滤，并对 Agent/API/MCP 隐藏 deprecated 别名。
- Agent Runtime 与 MCP Gateway 均保留完整 `CapabilityResult`：`ok`、`capability_id`、`version`、`data`、`error`、`evidence`、`audit`。
- 首批新增 Capability 全部保持 `plugin_callable=false`。第三方插件开放必须另行完成单项授权评审；本次不借消费者迁移扩大插件权限。

## 退役判定

本矩阵中的“代码迁移完成”不等于旧路由可删除。只有在测试部署完成调用观测、确认没有剩余消费者、完成 OceanBase/OIS 烟测并准备回滚方案后，才能把对应旧路径标记为“旧 API 已退役”。
