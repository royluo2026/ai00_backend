# AI00 Capability V2 开发者手册

本目录由不可变 Catalog Release 自动生成，不接受手工修改。

- Catalog Release：`rel_118d91d38b08fcecd96ddea0005a02b5`
- Catalog Hash：`sha256:118d91d38b08fcecd96ddea0005a02b5c81cc121f93b4028b33b15fe91bfb29f`
- 描述符数量：270

## 重要边界

只有 `exposure` 对目标消费者为 `true` 的能力才可调用。出现在 User Function Registry、网页路由或源码中，并不等于插件或 Agent 已获授权。当前文档如实显示迁移状态；禁止根据名称猜测能力、主版本、权限或参数。

调用必须固定 `catalog_release + capability_id + major_version`，使用服务端可信身份，经唯一 Gateway 执行。业务字符串对 Agent/MCP 均视为不可信数据。大文件使用 `ArtifactRef`，异步、本地、设备与长任务使用 `OperationRef`。

## 领域覆盖

| 领域 | 已进入 V2 Catalog |
|---|---:|
| `agent` | 13 |
| `base` | 47 |
| `craft` | 67 |
| `device` | 10 |
| `digital_model` | 8 |
| `factory` | 19 |
| `integration` | 13 |
| `knowledge` | 32 |
| `ontology` | 14 |
| `project_management` | 32 |
| `simulation` | 15 |

## 消费者可用数量

| 消费者 | 能力数 |
|---|---:|
| web | 270 |
| plugin | 267 |
| agent | 267 |
| api | 270 |
| mcp | 267 |
| worker | 1 |
| local_runtime | 7 |

## 文件

- `catalog.v2.json`：完整机器目录和最小合法示例。
- `agent-tools.v2.json`：仅包含 `exposure.agent=true` 的工具。
- `mcp-tools.v2.json`：仅包含 `exposure.mcp=true` 的工具。
- `openapi-fragment.v2.json`：固定 release 的 API Schema 片段。
- `INTEGRATION.md`、`SECURITY.md`、`ERRORS.md`：接入、安全和错误处理规范。
