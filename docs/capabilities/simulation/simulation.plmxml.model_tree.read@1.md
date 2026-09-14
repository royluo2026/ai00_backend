# simulation.plmxml.model_tree.read@1

Read one bounded page of the product occurrence tree from one authorized immutable PLMXML Artifact without mutating an environment.

## 使用判断

- 适用：Read one bounded page of the product occurrence tree from one authorized immutable PLMXML Artifact without mutating an environment.
- 不适用：Use the owning domain's governed Capability.
- 生命周期：`experimental`
- 所属领域：`simulation`
- Catalog Release：`<catalog_release>`（调用时使用 Host 当前固定的目录版本）
- Schema 精度：`typed`
- 暂未开放原因：`domain_errors_not_declared`, `experimental_lifecycle`

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
- `artifact` ← `artifact_ref.artifact_id`（必填）

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
- `collection_policy`：`paged`
- `max_page_size`：5000
- `max_parallel_per_consumer`：4
- `max_parallel_per_tenant`：32
- `overload_policy`：`reject`

## 输入 Schema

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_ref": {
      "additionalProperties": false,
      "properties": {
        "artifact_id": {
          "type": "string"
        },
        "byte_size": {
          "minimum": 0,
          "type": "integer"
        },
        "media_type": {
          "enum": [
            "application/plmxml+xml",
            "application/vnd.siemens.plmxml+xml"
          ],
          "type": "string"
        },
        "sha256": {
          "pattern": "^(sha256:)?[0-9a-f]{64}$",
          "type": "string"
        },
        "version": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "artifact_id",
        "media_type",
        "sha256",
        "byte_size",
        "version"
      ],
      "type": "object"
    },
    "dependency_artifacts": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "artifact_ref": {
            "additionalProperties": false,
            "properties": {
              "artifact_id": {
                "type": "string"
              },
              "byte_size": {
                "minimum": 0,
                "type": "integer"
              },
              "media_type": {
                "enum": [
                  "application/plmxml+xml",
                  "application/vnd.siemens.plmxml+xml",
                  "model/vnd.jt",
                  "model/jt"
                ],
                "type": "string"
              },
              "sha256": {
                "pattern": "^(sha256:)?[0-9a-f]{64}$",
                "type": "string"
              },
              "version": {
                "minimum": 1,
                "type": "integer"
              }
            },
            "required": [
              "artifact_id",
              "media_type",
              "sha256",
              "byte_size",
              "version"
            ],
            "type": "object"
          },
          "location": {
            "maxLength": 2048,
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "location",
          "artifact_ref"
        ],
        "type": "object"
      },
      "maxItems": 10000,
      "type": "array"
    },
    "limit": {
      "maximum": 5000,
      "minimum": 1,
      "type": "integer"
    },
    "offset": {
      "maximum": 250000,
      "minimum": 0,
      "type": "integer"
    }
  },
  "required": [
    "artifact_ref"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "simulation.plmxml.model_tree.read",
  "catalog_release": "<catalog_release>",
  "major_version": 1,
  "payload": {
    "artifact_ref": {
      "artifact_id": "example",
      "byte_size": 0,
      "media_type": "application/plmxml+xml",
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "version": 1
    }
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "dependency_locations": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "next_offset": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ]
    },
    "node_count": {
      "minimum": 0,
      "type": "integer"
    },
    "nodes": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "bom_line": {
            "type": "string"
          },
          "child_order": {
            "minimum": 0,
            "type": "integer"
          },
          "has_more": {
            "type": "boolean"
          },
          "item_id": {
            "type": "string"
          },
          "name": {
            "type": "string"
          },
          "node_key": {
            "type": "string"
          },
          "occurrence_id": {
            "type": "string"
          },
          "parent_key": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "revision": {
            "type": "string"
          }
        },
        "required": [
          "node_key",
          "parent_key",
          "child_order",
          "name",
          "bom_line",
          "item_id",
          "revision",
          "occurrence_id",
          "has_more"
        ],
        "type": "object"
      },
      "maxItems": 5000,
      "type": "array"
    },
    "state": {
      "enum": [
        "ready",
        "dependency_required"
      ],
      "type": "string"
    }
  },
  "required": [
    "state",
    "node_count",
    "nodes",
    "dependency_locations",
    "next_offset"
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

- `plmxml_artifact_hash_mismatch`：The PLMXML Artifact bytes do not match the immutable reference hash.（retryable=false）
- `plmxml_artifact_unavailable`：The immutable PLMXML Artifact is unavailable or outside the caller scope.（retryable=false）
- `plmxml_dependency_artifact_invalid`：A supplied PLMXML dependency Artifact reference is malformed or duplicated.（retryable=false）
- `plmxml_dependency_media_type_mismatch`：A dependency Artifact media type does not match the PLMXML reference.（retryable=false）
- `plmxml_dependency_artifact_unavailable`：A dependency Artifact is unavailable or outside the caller scope.（retryable=false）
- `plmxml_dependency_artifact_hash_mismatch`：A dependency Artifact does not match its immutable SHA-256 reference.（retryable=false）
- `plmxml_insert_mode_required`：PLMXML insertion requires an explicit model-only or selected-hierarchy mode.（retryable=false）
- `plmxml_hierarchy_selection_invalid`：The selected hierarchy identities are invalid for this inspected PLMXML.（retryable=false）
- `plmxml_inspection_changed`：The inspected PLMXML projection changed before the requested write.（retryable=false）

`domain_errors_complete=false`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
