# craft.standard_operation.change.apply@1

Apply bounded Craft standard operation lifecycle and content changes.

## 使用判断

- 适用：A governed consumer needs to create, update, publish, deprecate or delete a standard operation.
- 不适用：The change belongs to a GBOP release or BOP execution operation.
- 生命周期：`stable`
- 所属领域：`craft`
- Catalog Release：`rel_a09dc46bd385dfe188e3236dd882f6b3`
- Schema 精度：`typed`
- 暂未开放原因：无

## 消费者可用性

| 消费者 | 状态 |
|---|---|
| web | 可用 |
| plugin | 可用 |
| agent | 可用 |
| api | 可用 |
| mcp | 可用 |
| worker | 不可用 |
| local_runtime | 不可用 |

插件和 Agent 只有在上表对应值为“可用”，且安装/Mount 或 Delegation 明确授权时才可调用。

## 授权与数据边界

- 授权策略：`craft.v2:craft.write`
- 自动化等级：`A1`
- 数据分类：`confidential`
- Delegation：`scoped`
- 认证新鲜度：0 秒

资源选择器：
- 无资源选择器；仍受租户、身份与权限策略约束。

## 执行与可靠性

- 副作用：`write`
- 执行模式：`cloud_sync`
- 超时：30 秒
- 审批：`user`
- 幂等：`required`
- 并发：`none`
- 无预期版本信封要求。
- 一致性：`external`
- Operation：`optional`
- Artifact：`none`
- 审计：`standard`
- Evidence：`optional`
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
    "conflict": {
      "enum": [
        "skip",
        "overwrite",
        "append"
      ],
      "type": "string"
    },
    "gid": {
      "minLength": 1,
      "type": "string"
    },
    "operation": {
      "enum": [
        "create",
        "bulk_import",
        "update",
        "delete",
        "publish",
        "deprecate"
      ],
      "type": "string"
    },
    "record": {
      "additionalProperties": false,
      "properties": {
        "code": {
          "type": "string"
        },
        "description": {
          "type": "string"
        },
        "importance": {
          "type": "string"
        },
        "level": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "parameters": {
          "additionalProperties": false,
          "properties": {},
          "type": "object"
        },
        "parent_vpps": {
          "type": "string"
        },
        "required_tools": {
          "items": {
            "description": "Provider-validated tool reference."
          },
          "maxItems": 200,
          "type": "array"
        },
        "standard_time": {
          "minimum": 0,
          "type": "number"
        },
        "steps": {
          "items": {
            "description": "Provider-validated step."
          },
          "maxItems": 200,
          "type": "array"
        },
        "torque_importance": {
          "type": "string"
        },
        "vehicle_model": {
          "type": "string"
        },
        "vpps": {
          "type": "string"
        },
        "vpps_attr": {
          "type": "string"
        },
        "vpps_desc": {
          "type": "string"
        }
      },
      "type": "object"
    },
    "records": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "code": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "importance": {
            "type": "string"
          },
          "level": {
            "type": "string"
          },
          "name": {
            "type": "string"
          },
          "parameters": {
            "additionalProperties": false,
            "properties": {},
            "type": "object"
          },
          "parent_vpps": {
            "type": "string"
          },
          "required_tools": {
            "items": {
              "description": "Provider-validated tool reference."
            },
            "maxItems": 200,
            "type": "array"
          },
          "standard_time": {
            "minimum": 0,
            "type": "number"
          },
          "steps": {
            "items": {
              "description": "Provider-validated step."
            },
            "maxItems": 200,
            "type": "array"
          },
          "torque_importance": {
            "type": "string"
          },
          "vehicle_model": {
            "type": "string"
          },
          "vpps": {
            "type": "string"
          },
          "vpps_attr": {
            "type": "string"
          },
          "vpps_desc": {
            "type": "string"
          }
        },
        "type": "object"
      },
      "maxItems": 10000,
      "type": "array"
    }
  },
  "required": [
    "operation"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "craft.standard_operation.change.apply",
  "catalog_release": "rel_a09dc46bd385dfe188e3236dd882f6b3",
  "major_version": 1,
  "payload": {
    "operation": "create"
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "created_count": {
      "type": "integer"
    },
    "gid": {
      "minLength": 1,
      "type": "string"
    },
    "skipped_count": {
      "type": "integer"
    },
    "success": {
      "type": "boolean"
    },
    "updated_count": {
      "type": "integer"
    }
  },
  "required": [
    "success",
    "gid"
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

- `bop_version_not_found`：The scoped BOP version does not exist.（retryable=false）
- `bop_revision_unavailable`：The BOP has no authoritative revision.（retryable=false）
- `revision_conflict`：The current BOP revision differs from the expected revision.（retryable=false）
- `bop_entry_not_found`：A referenced BOP entry does not exist.（retryable=false）
- `bop_link_not_found`：A referenced BOP link does not exist.（retryable=false）
- `bop_project_unassigned`：The BOP is not assigned to a project.（retryable=false）
- `version_not_published`：An official execution structure requires a published BOP.（retryable=false）
- `preview_not_found`：The requested BOP change preview does not exist.（retryable=false）
- `preview_expired`：The requested BOP change preview has expired.（retryable=false）
- `preview_already_applied`：The requested BOP change preview was already committed.（retryable=false）
- `idempotency_conflict`：The idempotency key is already bound to another Craft payload.（retryable=false）
- `source_not_found`：The requested version creation source does not exist.（retryable=false）
- `archive_forbidden`：The BOP lifecycle forbids archiving this version.（retryable=false）
- `pbom_snapshot_not_found`：The scoped PBOM snapshot does not exist.（retryable=false）
- `active_gbop_not_found`：No active GBOP release exists.（retryable=false）
- `multiple_active_gbop_releases`：More than one active GBOP release exists.（retryable=false）
- `active_gbop_item_not_found`：The GBOP item is not in the active release.（retryable=false）
- `provider_unavailable`：The Craft application provider is unavailable.（retryable=false）
- `invalid_cursor`：The pagination cursor is invalid.（retryable=false）
- `invalid_page_size`：The requested page size is outside the capability limit.（retryable=false）
- `invalid_scope_kind`：The requested BOP scope kind is invalid.（retryable=false）
- `scope_not_found`：The requested BOP scope does not exist in the version.（retryable=false）
- `entry_not_found`：The requested BOP entry does not exist in the version.（retryable=false）
- `entry_detail_too_large`：The BOP entry has too many links for bounded detail output.（retryable=false）
- `rule_not_found`：The requested rule was not found.（retryable=false）
- `evaluation_timeout`：Rule evaluation exceeded its bounded time limit.（retryable=false）
- `evaluation_unavailable`：Rule evaluation could not produce a bounded result.（retryable=false）
- `resource_not_found`：The requested active Craft resource requirement does not exist.（retryable=false）
- `resource_code_conflict`：The resource type and code already identify another standard.（retryable=false）
- `resource_version_conflict`：The resource requirement changed or is no longer active.（retryable=false）
- `resource_in_use`：The resource requirement is still referenced by governed Craft data.（retryable=false）
- `resource_alias_conflict`：The normalized alias already exists for this resource.（retryable=false）
- `resource_alias_not_found`：The requested resource alias does not exist.（retryable=false）
- `resource_staging_not_found`：The requested TC resource staging row does not exist.（retryable=false）
- `resource_staging_conflict`：The staging row was already decided or changed.（retryable=false）
- `resource_type_mismatch`：The selected standard does not match the staged resource type.（retryable=false）
- `screenshot_artifact_invalid`：The supplied screenshot is not a valid finalized image ArtifactRef.（retryable=false）

`domain_errors_complete=true`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
