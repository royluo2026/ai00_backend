# simulation.environment.bop_projection.preview@1

Preview a deterministic BOP skeleton projection from an exact published or explicitly selected active Craft execution structure without copying product or resource references as hierarchy nodes.

## 使用判断

- 适用：Preview a deterministic BOP skeleton projection from an exact published or explicitly selected active Craft execution structure without copying product or resource references as hierarchy nodes.
- 不适用：Use the owning domain's governed Capability.
- 生命周期：`experimental`
- 所属领域：`simulation`
- Catalog Release：`<catalog_release>`（调用时使用 Host 当前固定的目录版本）
- Schema 精度：`typed`
- 暂未开放原因：`experimental_lifecycle`

## 消费者可用性

| 消费者 | 状态 |
|---|---|
| web | 可用 |
| plugin | 不可用 |
| agent | 不可用 |
| api | 不可用 |
| mcp | 不可用 |
| worker | 不可用 |
| local_runtime | 不可用 |

插件和 Agent 只有在上表对应值为“可用”，且安装/Mount 或 Delegation 明确授权时才可调用。

## 授权与数据边界

- 授权策略：`simulation.v2:simulation.use`
- 自动化等级：`A2`
- 数据分类：`confidential`
- Delegation：`scoped`
- 认证新鲜度：0 秒

资源选择器：
- `simulation-workspace` ← `workspace_gid`（必填）
- `craft-bop-version` ← `version_gid`（必填）

## 执行与可靠性

- 副作用：`read`
- 执行模式：`cloud_sync`
- 超时：30 秒
- 审批：`none`
- 幂等：`none`
- 并发：`none`
- 无预期版本信封要求。
- 一致性：`strong`
- Operation：`none`
- Artifact：`none`
- 审计：`standard`
- Evidence：`required`
- 配额成本：1

资源预算：

- `memory_class`：`small`
- `max_input_bytes`：1048576
- `max_output_bytes`：4194304
- `collection_policy`：`bounded`
- `max_page_size`：None
- `max_parallel_per_consumer`：4
- `max_parallel_per_tenant`：32
- `overload_policy`：`reject`

## 输入 Schema

```json
{
  "additionalProperties": false,
  "properties": {
    "expected_row_version": {
      "minimum": 1,
      "type": "integer"
    },
    "fork_depth": {
      "enum": [
        "all",
        "operation",
        "process",
        "role",
        "station"
      ],
      "type": "string"
    },
    "hierarchy_name": {
      "maxLength": 255,
      "minLength": 1,
      "type": "string"
    },
    "line_gid": {
      "anyOf": [
        {
          "pattern": "^[1-9][0-9]*$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "version_gid": {
      "pattern": "^[1-9][0-9]*$",
      "type": "string"
    },
    "workspace_gid": {
      "pattern": "^[1-9][0-9]*$",
      "type": "string"
    }
  },
  "required": [
    "workspace_gid",
    "version_gid",
    "line_gid",
    "fork_depth",
    "hierarchy_name",
    "expected_row_version"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "simulation.environment.bop_projection.preview",
  "catalog_release": "<catalog_release>",
  "major_version": 1,
  "payload": {
    "expected_row_version": 1,
    "fork_depth": "all",
    "hierarchy_name": "example",
    "line_gid": "1",
    "version_gid": "1",
    "workspace_gid": "1"
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "conflicts": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "code": {
            "type": "string"
          },
          "detail": {
            "type": "string"
          }
        },
        "required": [
          "code"
        ],
        "type": "object"
      },
      "maxItems": 1000,
      "type": "array"
    },
    "expected_workspace_version": {
      "minimum": 1,
      "type": "integer"
    },
    "fork_depth": {
      "enum": [
        "all",
        "operation",
        "process",
        "role",
        "station"
      ],
      "type": "string"
    },
    "hierarchy_name": {
      "type": "string"
    },
    "line_gid": {
      "anyOf": [
        {
          "pattern": "^[1-9][0-9]*$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "model_reference_count": {
      "minimum": 0,
      "type": "integer"
    },
    "model_references": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "reference": {
            "maxLength": 255,
            "minLength": 1,
            "type": "string"
          },
          "source_node_gid": {
            "pattern": "^[1-9][0-9]*$",
            "type": "string"
          }
        },
        "required": [
          "source_node_gid",
          "reference"
        ],
        "type": "object"
      },
      "maxItems": 10000,
      "type": "array"
    },
    "node_count": {
      "minimum": 0,
      "type": "integer"
    },
    "nodes": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "name": {
            "maxLength": 255,
            "minLength": 1,
            "type": "string"
          },
          "node_type": {
            "maxLength": 32,
            "minLength": 1,
            "type": "string"
          },
          "parent_source_gid": {
            "anyOf": [
              {
                "pattern": "^[1-9][0-9]*$",
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "position": {
            "minimum": 0,
            "type": "integer"
          },
          "source_gid": {
            "pattern": "^[1-9][0-9]*$",
            "type": "string"
          }
        },
        "required": [
          "source_gid",
          "parent_source_gid",
          "node_type",
          "name",
          "position"
        ],
        "type": "object"
      },
      "maxItems": 10000,
      "type": "array"
    },
    "plan_hash": {
      "pattern": "^(sha256:)?[0-9a-f]{64}$",
      "type": "string"
    },
    "resource_reference_count": {
      "minimum": 0,
      "type": "integer"
    },
    "resource_references": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "reference": {
            "maxLength": 255,
            "minLength": 1,
            "type": "string"
          },
          "resource_type": {
            "enum": [
              "tool",
              "fixture",
              "equipment"
            ],
            "type": "string"
          },
          "source_node_gid": {
            "pattern": "^[1-9][0-9]*$",
            "type": "string"
          }
        },
        "required": [
          "source_node_gid",
          "resource_type",
          "reference"
        ],
        "type": "object"
      },
      "maxItems": 10000,
      "type": "array"
    },
    "source_content_hash": {
      "pattern": "^(sha256:)?[0-9a-f]{64}$",
      "type": "string"
    },
    "source_project_gid": {
      "pattern": "^[1-9][0-9]*$",
      "type": "string"
    },
    "source_revision": {
      "minimum": 1,
      "type": "integer"
    },
    "source_version_gid": {
      "pattern": "^[1-9][0-9]*$",
      "type": "string"
    },
    "workspace_gid": {
      "pattern": "^[1-9][0-9]*$",
      "type": "string"
    }
  },
  "required": [
    "workspace_gid",
    "expected_workspace_version",
    "source_project_gid",
    "source_version_gid",
    "source_revision",
    "source_content_hash",
    "line_gid",
    "fork_depth",
    "hierarchy_name",
    "nodes",
    "node_count",
    "model_references",
    "resource_references",
    "model_reference_count",
    "resource_reference_count",
    "conflicts",
    "plan_hash"
  ],
  "type": "object"
}
```

## 错误

- `catalog_resolution_failed`：目录 release、能力 ID 或主版本无法解析。
- `consumer_not_allowed`：当前消费者类型未获 exposure 授权。
- `authorization_failed`：授权后端不可用或无法形成可信决策。
- `permission_denied`：调用者缺少能力要求的权限。
- `tenant_scope_denied`：身份与授权租户不一致。
- `resource_scope_denied`：目标资源不在授权或 Delegation 范围内。
- `data_scope_denied`：数据分类不在授权范围内。
- `delegation_required`：Agent/委托消费者缺少服务端 Delegation。
- `delegation_expired`：Delegation 已过期。
- `resource_selector_missing`：描述符要求的资源定位字段缺失。
- `resource_selector_invalid`：资源定位字段不是允许的标量标识。
- `invalid_input`：请求不符合该 release 中冻结的输入 Schema。
- `expected_resource_version_required`：该能力要求信封提供预期资源版本。
- `expected_resource_version_payload_missing`：描述符声明的基线版本字段未出现在 payload。
- `expected_resource_version_mismatch`：信封预期版本与 payload 基线版本不一致。
- `confirmation_required`：写操作需要绑定本次请求的一次性审批。
- `confirmation_rejected`：审批无效、已用、已过期或与请求绑定不一致。
- `idempotency_key_required`：描述符要求写请求提供幂等键。
- `idempotency_payload_conflict`：同一幂等范围被用于不同 payload。
- `idempotency_in_progress`：同一幂等请求仍在执行。
- `rate_limit_exceeded`：租户及消费者配额不足，可按 retryable 指示重试。
- `transaction_participant_required`：强一致写 Provider 未加入领域事务。
- `provider_failed`：领域 Provider 执行失败；错误正文不会泄露内部细节。
- `outcome_persistence_failed`：领域可能已提交但 Outcome 未能确认，必须查询 OperationRef。
- `operation_service_unavailable`：能力要求异步 Operation，但持久化 Operation 服务未配置。
- `operation_create_failed`：异步 Operation 无法持久化，领域任务未派发。
- `operation_create_outcome_failed`：异步 Operation 创建后的命令 Outcome 无法持久化，领域任务未派发。

领域错误：

- `workspace_not_found`：The target Simulation environment is unavailable or not owned by the caller.（retryable=false）
- `version_conflict`：The target environment row version changed.（retryable=true）
- `fork_depth_invalid`：The requested BOP projection depth is unsupported.（retryable=false）
- `bop_projection_hash_invalid`：The Craft execution structure has no valid immutable hash.（retryable=false）
- `bop_projection_node_invalid`：The Craft execution structure contains an invalid node.（retryable=false）
- `bop_projection_line_not_found`：The requested line is not present in the exact Craft execution structure.（retryable=false）
- `bop_projection_parent_missing`：The projected process skeleton references a missing parent.（retryable=false）
- `bop_projection_cycle`：The projected process skeleton contains a cycle.（retryable=false）
- `bop_projection_plan_changed`：The exact preview no longer matches the current source or target.（retryable=true）
- `bop_projection_already_inserted`：The exact BOP projection is already present in the target environment.（retryable=false）
- `bop_execution_structure_failed`：The owning Craft capability could not return the exact revision-pinned execution structure.（retryable=true）
- `bop_version_resolution_failed`：The owning Craft capability could not resolve the selected BOP revision.（retryable=true）
- `bop_revision_unavailable`：The selected BOP did not expose a valid revision for a draft preview.（retryable=false）
- `domain_client_unavailable`：The governed owning-domain invocation boundary is unavailable.（retryable=true）
- `idempotency_conflict`：The idempotency key is bound to another BOP projection request.（retryable=false）

`domain_errors_complete=true`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
