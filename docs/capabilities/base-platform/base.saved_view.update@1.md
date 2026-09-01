# base.saved_view.update@1

Execute exact Base outcome base.saved_view.update.

## 使用判断

- 适用：A browser consumer needs exactly this Base-owned outcome.
- 不适用：The request selects another operation or domain.
- 生命周期：`stable`
- 所属领域：`base`
- Catalog Release：`rel_3f5ef8265738dc99f4803579111af53d`
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

- 授权策略：`base.v2:authenticated`
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
- 一致性：`strong`
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
    "config": {
      "additionalProperties": false,
      "properties": {
        "field_gids": {
          "items": {
            "maxLength": 512,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 200,
          "type": "array",
          "uniqueItems": true
        },
        "filters": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "field_gid": {
                "maxLength": 512,
                "minLength": 1,
                "type": "string"
              },
              "operator": {
                "enum": [
                  "contains",
                  "not_contains",
                  "eq",
                  "not_eq",
                  "empty",
                  "not_empty",
                  "gt",
                  "gte",
                  "lt",
                  "lte"
                ],
                "type": "string"
              },
              "value": {
                "anyOf": [
                  {
                    "maxLength": 2000,
                    "type": "string"
                  },
                  {
                    "type": "number"
                  },
                  {
                    "type": "boolean"
                  },
                  {
                    "type": "null"
                  },
                  {
                    "items": {
                      "type": [
                        "string",
                        "number",
                        "boolean",
                        "null"
                      ]
                    },
                    "maxItems": 100,
                    "type": "array"
                  }
                ]
              }
            },
            "required": [
              "field_gid",
              "operator",
              "value"
            ],
            "type": "object"
          },
          "maxItems": 50,
          "type": "array"
        },
        "page_size": {
          "maximum": 200,
          "minimum": 1,
          "type": "integer"
        },
        "presentation": {
          "enum": [
            "table",
            "list"
          ],
          "type": "string"
        },
        "sort": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "direction": {
                "enum": [
                  "asc",
                  "desc"
                ],
                "type": "string"
              },
              "field_gid": {
                "maxLength": 512,
                "minLength": 1,
                "type": "string"
              }
            },
            "required": [
              "field_gid",
              "direction"
            ],
            "type": "object"
          },
          "maxItems": 20,
          "type": "array"
        }
      },
      "required": [
        "field_gids",
        "filters",
        "sort",
        "page_size",
        "presentation"
      ],
      "type": "object"
    },
    "expected_revision": {
      "minimum": 1,
      "type": "integer"
    },
    "idempotency_key": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    },
    "list_gid": {
      "maxLength": 512,
      "type": [
        "string",
        "null"
      ]
    },
    "module": {
      "maxLength": 255,
      "type": "string"
    },
    "name": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    },
    "share_scope": {
      "enum": [
        "private",
        "team",
        "shared"
      ],
      "type": "string"
    },
    "view_gid": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "view_gid",
    "expected_revision",
    "name",
    "config",
    "idempotency_key"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "base.saved_view.update",
  "catalog_release": "rel_3f5ef8265738dc99f4803579111af53d",
  "major_version": 1,
  "payload": {
    "config": {
      "field_gids": [],
      "filters": [],
      "page_size": 1,
      "presentation": "table",
      "sort": []
    },
    "expected_revision": 1,
    "idempotency_key": "example",
    "name": "example",
    "view_gid": "example"
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "view": {
      "additionalProperties": false,
      "properties": {
        "config": {
          "additionalProperties": false,
          "properties": {
            "field_gids": {
              "items": {
                "maxLength": 512,
                "minLength": 1,
                "type": "string"
              },
              "maxItems": 200,
              "type": "array",
              "uniqueItems": true
            },
            "filters": {
              "items": {
                "additionalProperties": false,
                "properties": {
                  "field_gid": {
                    "maxLength": 512,
                    "minLength": 1,
                    "type": "string"
                  },
                  "operator": {
                    "enum": [
                      "contains",
                      "not_contains",
                      "eq",
                      "not_eq",
                      "empty",
                      "not_empty",
                      "gt",
                      "gte",
                      "lt",
                      "lte"
                    ],
                    "type": "string"
                  },
                  "value": {
                    "anyOf": [
                      {
                        "maxLength": 2000,
                        "type": "string"
                      },
                      {
                        "type": "number"
                      },
                      {
                        "type": "boolean"
                      },
                      {
                        "type": "null"
                      },
                      {
                        "items": {
                          "type": [
                            "string",
                            "number",
                            "boolean",
                            "null"
                          ]
                        },
                        "maxItems": 100,
                        "type": "array"
                      }
                    ]
                  }
                },
                "required": [
                  "field_gid",
                  "operator",
                  "value"
                ],
                "type": "object"
              },
              "maxItems": 50,
              "type": "array"
            },
            "page_size": {
              "maximum": 200,
              "minimum": 1,
              "type": "integer"
            },
            "presentation": {
              "enum": [
                "table",
                "list"
              ],
              "type": "string"
            },
            "sort": {
              "items": {
                "additionalProperties": false,
                "properties": {
                  "direction": {
                    "enum": [
                      "asc",
                      "desc"
                    ],
                    "type": "string"
                  },
                  "field_gid": {
                    "maxLength": 512,
                    "minLength": 1,
                    "type": "string"
                  }
                },
                "required": [
                  "field_gid",
                  "direction"
                ],
                "type": "object"
              },
              "maxItems": 20,
              "type": "array"
            }
          },
          "required": [
            "field_gids",
            "filters",
            "sort",
            "page_size",
            "presentation"
          ],
          "type": "object"
        },
        "deleted": {
          "type": "boolean"
        },
        "gid": {
          "maxLength": 512,
          "minLength": 1,
          "type": "string"
        },
        "grants": {
          "items": {
            "maxLength": 512,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 200,
          "type": "array"
        },
        "list_gid": {
          "maxLength": 512,
          "type": [
            "string",
            "null"
          ]
        },
        "module": {
          "maxLength": 255,
          "type": "string"
        },
        "name": {
          "maxLength": 512,
          "minLength": 1,
          "type": "string"
        },
        "owner_gid": {
          "maxLength": 512,
          "minLength": 1,
          "type": "string"
        },
        "restore": {
          "additionalProperties": false,
          "properties": {
            "available": {
              "type": "boolean"
            },
            "deleted_at": {
              "maxLength": 64,
              "type": "string"
            },
            "deleted_by": {
              "maxLength": 512,
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "available",
            "deleted_by",
            "deleted_at"
          ],
          "type": [
            "object",
            "null"
          ]
        },
        "revision": {
          "minimum": 1,
          "type": "integer"
        },
        "share_scope": {
          "enum": [
            "private",
            "team",
            "shared"
          ],
          "type": "string"
        }
      },
      "required": [
        "gid",
        "name",
        "module",
        "list_gid",
        "owner_gid",
        "config",
        "revision",
        "deleted",
        "share_scope",
        "grants",
        "restore"
      ],
      "type": "object"
    }
  },
  "required": [
    "view"
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

- `idempotency_conflict`：base.saved_view.update can return idempotency_conflict.（retryable=false）
- `invalid_input`：base.saved_view.update can return invalid_input.（retryable=false）
- `legacy_config_unsupported`：base.saved_view.update can return legacy_config_unsupported.（retryable=false）
- `permission_denied`：base.saved_view.update can return permission_denied.（retryable=false）
- `resource_not_found`：base.saved_view.update can return resource_not_found.（retryable=false）
- `revision_conflict`：base.saved_view.update can return revision_conflict.（retryable=false）

`domain_errors_complete=true`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
