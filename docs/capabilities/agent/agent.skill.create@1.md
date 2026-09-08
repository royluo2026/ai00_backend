# agent.skill.create@1

Creates one owned Skill with a named prompt, tool, flow or canvas content model.

## 使用判断

- 适用：Creates one owned Skill with a named prompt, tool, flow or canvas content model.
- 不适用：Another business effect is requested.
- 生命周期：`stable`
- 所属领域：`agent`
- Catalog Release：`rel_74f4926ccfa6bc3588ec1c956dc25a5e`
- Schema 精度：`typed`
- 暂未开放原因：无

## 消费者可用性

| 消费者 | 状态 |
|---|---|
| web | 可用 |
| plugin | 不可用 |
| agent | 不可用 |
| api | 可用 |
| mcp | 不可用 |
| worker | 不可用 |
| local_runtime | 不可用 |

插件和 Agent 只有在上表对应值为“可用”，且安装/Mount 或 Delegation 明确授权时才可调用。

## 授权与数据边界

- 授权策略：`agent.v2:agent.interact`
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
- 一致性：`eventual`
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
  "$defs": {
    "parameter_schema": {
      "additionalProperties": false,
      "properties": {
        "additionalProperties": {
          "const": false
        },
        "default": {
          "type": [
            "string",
            "number",
            "boolean",
            "null"
          ]
        },
        "description": {
          "maxLength": 4096,
          "type": "string"
        },
        "enum": {
          "items": {
            "type": [
              "string",
              "number",
              "boolean",
              "null"
            ]
          },
          "maxItems": 64,
          "type": "array"
        },
        "format": {
          "maxLength": 4096,
          "type": "string"
        },
        "items": {
          "$ref": "#/$defs/parameter_schema"
        },
        "maxItems": {
          "maximum": 128,
          "minimum": 0,
          "type": "integer"
        },
        "maxLength": {
          "maximum": 65536,
          "minimum": 0,
          "type": "integer"
        },
        "maximum": {
          "type": "number"
        },
        "minItems": {
          "minimum": 0,
          "type": "integer"
        },
        "minLength": {
          "minimum": 0,
          "type": "integer"
        },
        "minimum": {
          "type": "number"
        },
        "properties": {
          "additionalProperties": false,
          "maxProperties": 64,
          "patternProperties": {
            "^[A-Za-z][A-Za-z0-9_.-]{0,127}$": {
              "$ref": "#/$defs/parameter_schema"
            }
          },
          "type": "object"
        },
        "required": {
          "items": {
            "maxLength": 256,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 64,
          "type": "array"
        },
        "title": {
          "maxLength": 4096,
          "type": "string"
        },
        "type": {
          "enum": [
            "object",
            "array",
            "string",
            "number",
            "integer",
            "boolean",
            "null"
          ]
        }
      },
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "content": {
      "additionalProperties": false,
      "properties": {
        "canvas": {
          "additionalProperties": false,
          "properties": {
            "connections": {
              "items": {
                "additionalProperties": false,
                "properties": {
                  "from": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "fromPort": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "id": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "to": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "toPort": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "type": {
                    "maxLength": 4096,
                    "type": "string"
                  }
                },
                "required": [
                  "id",
                  "from",
                  "to",
                  "type"
                ],
                "type": "object"
              },
              "maxItems": 256,
              "type": "array"
            },
            "lanes": {
              "items": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 256,
                    "minLength": 1,
                    "type": "string"
                  },
                  "label": {
                    "maxLength": 4096,
                    "type": "string"
                  }
                },
                "required": [
                  "id",
                  "label"
                ],
                "type": "object"
              },
              "maxItems": 128,
              "type": "array"
            },
            "nodes": {
              "items": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 256,
                    "minLength": 1,
                    "type": "string"
                  },
                  "label": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "laneIdx": {
                    "maximum": 127,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "lane_id": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "params": {
                    "additionalProperties": false,
                    "properties": {
                      "_items": {
                        "items": {
                          "additionalProperties": false,
                          "properties": {
                            "description": {
                              "maxLength": 4096,
                              "type": "string"
                            },
                            "gid": {
                              "maxLength": 4096,
                              "type": "string"
                            },
                            "item_type": {
                              "maxLength": 4096,
                              "type": "string"
                            },
                            "name": {
                              "maxLength": 4096,
                              "type": "string"
                            },
                            "status": {
                              "maxLength": 4096,
                              "type": "string"
                            },
                            "title": {
                              "maxLength": 4096,
                              "type": "string"
                            },
                            "url": {
                              "maxLength": 4096,
                              "type": "string"
                            }
                          },
                          "type": "object"
                        },
                        "maxItems": 128,
                        "type": "array"
                      },
                      "access": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "agent_name": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "approver": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "assignee": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "branches": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "condition_expr": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "confirm_required": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "db": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "domain": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "false_branch": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "format": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "item_query": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "list_gid": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "note": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "params_hint": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "path": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "scope": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "skill_gid": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "skill_name": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "strategy": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "table": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "task_desc": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "tool_name": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "true_branch": {
                        "maxLength": 4096,
                        "type": "string"
                      },
                      "var_name": {
                        "maxLength": 4096,
                        "type": "string"
                      }
                    },
                    "type": "object"
                  },
                  "step": {
                    "maximum": 127,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "type": {
                    "enum": [
                      "agent",
                      "human",
                      "tool_read",
                      "tool_write",
                      "skill_call",
                      "fork",
                      "join",
                      "condition",
                      "list",
                      "data_db",
                      "data_mem",
                      "data_file",
                      "human_approval",
                      "human_task",
                      "result_list"
                    ]
                  },
                  "x": {
                    "type": "number"
                  },
                  "y": {
                    "type": "number"
                  }
                },
                "required": [
                  "id",
                  "type",
                  "label",
                  "params"
                ],
                "type": "object"
              },
              "maxItems": 128,
              "type": "array"
            },
            "questions": {
              "items": {
                "additionalProperties": false,
                "properties": {
                  "answer": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "id": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "nodeId": {
                    "maxLength": 4096,
                    "type": "string"
                  },
                  "text": {
                    "maxLength": 4096,
                    "type": "string"
                  }
                },
                "required": [
                  "id",
                  "text",
                  "answer"
                ],
                "type": "object"
              },
              "maxItems": 128,
              "type": "array"
            },
            "step_labels": {
              "items": {
                "maxLength": 4096,
                "type": "string"
              },
              "maxItems": 128,
              "type": "array"
            },
            "steps": {
              "maximum": 128,
              "minimum": 0,
              "type": "integer"
            },
            "title": {
              "maxLength": 4096,
              "type": "string"
            }
          },
          "type": "object"
        },
        "description": {
          "maxLength": 4096,
          "type": "string"
        },
        "flow_gid": {
          "maxLength": 4096,
          "type": "string"
        },
        "input_schema": {
          "$ref": "#/$defs/parameter_schema"
        },
        "need_confirm": {
          "type": "boolean"
        },
        "script": {
          "maxLength": 65536,
          "type": "string"
        },
        "system_hint": {
          "maxLength": 65536,
          "type": "string"
        },
        "template": {
          "maxLength": 65536,
          "type": "string"
        },
        "variables": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "default": {
                "maxLength": 4096,
                "type": "string"
              },
              "label": {
                "maxLength": 4096,
                "type": "string"
              },
              "name": {
                "maxLength": 256,
                "minLength": 1,
                "type": "string"
              },
              "required": {
                "type": "boolean"
              }
            },
            "required": [
              "name",
              "label",
              "required",
              "default"
            ],
            "type": "object"
          },
          "maxItems": 64,
          "type": "array"
        }
      },
      "type": "object"
    },
    "description": {
      "maxLength": 4096,
      "type": "string"
    },
    "icon": {
      "maxLength": 4096,
      "type": "string"
    },
    "name": {
      "pattern": "^[a-z][a-z0-9_]{1,49}$",
      "type": "string"
    },
    "skill_type": {
      "enum": [
        "prompt",
        "tool",
        "flow"
      ]
    },
    "sort_order": {
      "type": "integer"
    },
    "tags": {
      "items": {
        "maxLength": 256,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 64,
      "type": "array"
    },
    "title": {
      "maxLength": 256,
      "minLength": 1,
      "type": "string"
    },
    "visibility": {
      "enum": [
        "private",
        "team",
        "global"
      ]
    }
  },
  "required": [
    "name",
    "title",
    "skill_type",
    "content"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "agent.skill.create",
  "catalog_release": "rel_74f4926ccfa6bc3588ec1c956dc25a5e",
  "major_version": 1,
  "payload": {
    "content": {},
    "name": "example",
    "skill_type": "prompt",
    "title": "example"
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "gid": {
      "maxLength": 256,
      "minLength": 1,
      "type": "string"
    },
    "success": {
      "const": true
    }
  },
  "required": [
    "success"
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

- `invalid_input`：The Agent request is invalid.（retryable=false）
- `permission_denied`：The caller cannot access the Agent resource.（retryable=false）
- `resource_not_found`：The Agent resource does not exist.（retryable=false）
- `version_conflict`：The Agent resource changed concurrently.（retryable=false）
- `catalog_release_unavailable`：The pinned Catalog release is unavailable.（retryable=true）
- `delegation_expired`：The Agent delegation is missing or expired.（retryable=false）
- `approval_required`：The delegated operation requires Base approval.（retryable=false）
- `provider_unavailable`：The Agent canvas runtime adapter is unavailable.（retryable=true）
- `runtime_timeout`：The bounded Agent canvas runtime timed out.（retryable=true）
- `idempotency_conflict`：The Agent canvas invocation conflicts with an earlier request.（retryable=false）
- `outcome_unknown`：The Agent canvas outcome must be reconciled.（retryable=true）

`domain_errors_complete=true`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
